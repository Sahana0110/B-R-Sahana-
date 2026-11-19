-- =====================================================================
-- ClaimSure : Insurance Policy and Claims Analytics
-- DBMS for Analytics Mini Project (25MSDA1S04)
-- Target: MySQL 8.0+   (run with:  mysql -u root -p < sql/schema.sql)
-- Design: 3NF, 9 tables, 2 views, 2 triggers
-- =====================================================================

DROP DATABASE IF EXISTS claimsure;
CREATE DATABASE claimsure CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE claimsure;

-- ---------------------------------------------------------------------
-- Lookup tables
-- ---------------------------------------------------------------------
CREATE TABLE regions (
    region_id     INT AUTO_INCREMENT PRIMARY KEY,
    region_name   VARCHAR(30) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE policy_types (
    policy_type_id INT AUTO_INCREMENT PRIMARY KEY,
    type_name      VARCHAR(30)   NOT NULL UNIQUE,
    base_rate      DECIMAL(6,4)  NOT NULL CHECK (base_rate > 0)   -- premium as fraction of sum insured
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- People
-- ---------------------------------------------------------------------
CREATE TABLE agents (
    agent_id    INT AUTO_INCREMENT PRIMARY KEY,
    full_name   VARCHAR(80)  NOT NULL,
    email       VARCHAR(100) NOT NULL UNIQUE,
    region_id   INT          NOT NULL,
    hire_date   DATE         NOT NULL,
    CONSTRAINT fk_agent_region FOREIGN KEY (region_id) REFERENCES regions(region_id)
) ENGINE=InnoDB;

CREATE TABLE customers (
    customer_id    INT AUTO_INCREMENT PRIMARY KEY,
    full_name      VARCHAR(80)  NOT NULL,
    email          VARCHAR(100) NOT NULL UNIQUE,
    phone          VARCHAR(15),
    date_of_birth  DATE         NOT NULL,
    city           VARCHAR(50)  NOT NULL,
    region_id      INT          NOT NULL,
    created_on     DATE         NOT NULL,
    CONSTRAINT fk_customer_region FOREIGN KEY (region_id) REFERENCES regions(region_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Policies and premiums
-- ---------------------------------------------------------------------
CREATE TABLE policies (
    policy_id       INT AUTO_INCREMENT PRIMARY KEY,
    policy_number   VARCHAR(15)   NOT NULL UNIQUE,
    customer_id     INT           NOT NULL,
    agent_id        INT           NOT NULL,
    policy_type_id  INT           NOT NULL,
    start_date      DATE          NOT NULL,
    end_date        DATE          NOT NULL,
    sum_insured     DECIMAL(14,2) NOT NULL CHECK (sum_insured > 0),
    annual_premium  DECIMAL(12,2) NOT NULL CHECK (annual_premium > 0),
    status          ENUM('ACTIVE','LAPSED','EXPIRED','CANCELLED') NOT NULL,
    CONSTRAINT chk_policy_dates CHECK (end_date > start_date),
    CONSTRAINT fk_policy_customer FOREIGN KEY (customer_id)    REFERENCES customers(customer_id),
    CONSTRAINT fk_policy_agent    FOREIGN KEY (agent_id)       REFERENCES agents(agent_id),
    CONSTRAINT fk_policy_type     FOREIGN KEY (policy_type_id) REFERENCES policy_types(policy_type_id),
    INDEX idx_policy_status (status),
    INDEX idx_policy_agent (agent_id)
) ENGINE=InnoDB;

CREATE TABLE premiums (
    premium_id  INT AUTO_INCREMENT PRIMARY KEY,
    policy_id   INT           NOT NULL,
    due_date    DATE          NOT NULL,
    paid_date   DATE,
    amount      DECIMAL(12,2) NOT NULL CHECK (amount > 0),
    status      ENUM('PAID','PENDING','OVERDUE') NOT NULL,
    CONSTRAINT fk_premium_policy FOREIGN KEY (policy_id) REFERENCES policies(policy_id),
    INDEX idx_premium_policy (policy_id),
    INDEX idx_premium_status (status)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Claims and settlements
-- ---------------------------------------------------------------------
CREATE TABLE claims (
    claim_id        INT AUTO_INCREMENT PRIMARY KEY,
    claim_number    VARCHAR(15)   NOT NULL UNIQUE,
    policy_id       INT           NOT NULL,
    incident_date   DATE          NOT NULL,
    claim_date      DATE          NOT NULL,
    claim_type      VARCHAR(40)   NOT NULL,
    claimed_amount  DECIMAL(14,2) NOT NULL CHECK (claimed_amount > 0),
    status          ENUM('SUBMITTED','UNDER_REVIEW','APPROVED','REJECTED','SETTLED') NOT NULL DEFAULT 'SUBMITTED',
    CONSTRAINT chk_claim_dates CHECK (claim_date >= incident_date),
    CONSTRAINT fk_claim_policy FOREIGN KEY (policy_id) REFERENCES policies(policy_id),
    INDEX idx_claim_policy (policy_id),
    INDEX idx_claim_status (status)
) ENGINE=InnoDB;

CREATE TABLE settlements (
    settlement_id   INT AUTO_INCREMENT PRIMARY KEY,
    claim_id        INT           NOT NULL UNIQUE,          -- one settlement per claim
    settled_date    DATE          NOT NULL,
    settled_amount  DECIMAL(14,2) NOT NULL CHECK (settled_amount >= 0),
    payment_mode    VARCHAR(20)   NOT NULL,
    CONSTRAINT fk_settlement_claim FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
) ENGINE=InnoDB;

-- Audit table filled by trigger
CREATE TABLE claim_status_log (
    log_id      INT AUTO_INCREMENT PRIMARY KEY,
    claim_id    INT         NOT NULL,
    old_status  VARCHAR(20) NOT NULL,
    new_status  VARCHAR(20) NOT NULL,
    changed_at  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_log_claim FOREIGN KEY (claim_id) REFERENCES claims(claim_id),
    INDEX idx_log_claim (claim_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------
DELIMITER $$

-- 1) Log every change of claim status
CREATE TRIGGER trg_claim_status_log
AFTER UPDATE ON claims
FOR EACH ROW
BEGIN
    IF OLD.status <> NEW.status THEN
        INSERT INTO claim_status_log (claim_id, old_status, new_status)
        VALUES (OLD.claim_id, OLD.status, NEW.status);
    END IF;
END$$

-- 2) Inserting a settlement automatically marks the claim as SETTLED
--    (this in turn fires trigger 1, so the change is logged)
CREATE TRIGGER trg_settlement_marks_claim
AFTER INSERT ON settlements
FOR EACH ROW
BEGIN
    UPDATE claims
       SET status = 'SETTLED'
     WHERE claim_id = NEW.claim_id
       AND status <> 'SETTLED';
END$$

DELIMITER ;

-- ---------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------
-- Per-policy financials (aggregates first, then join -> no row fan-out)
CREATE VIEW v_policy_financials AS
SELECT  p.policy_id,
        p.policy_number,
        p.policy_type_id,
        p.agent_id,
        p.customer_id,
        p.status                          AS policy_status,
        COALESCE(pr.premium_paid, 0)      AS premium_paid,
        COALESCE(cl.claims_count, 0)      AS claims_count,
        COALESCE(cl.claimed_total, 0)     AS claimed_total,
        COALESCE(st.settled_total, 0)     AS settled_total
FROM policies p
LEFT JOIN (SELECT policy_id, SUM(amount) AS premium_paid
           FROM premiums WHERE status = 'PAID' GROUP BY policy_id) pr ON pr.policy_id = p.policy_id
LEFT JOIN (SELECT policy_id, COUNT(*) AS claims_count, SUM(claimed_amount) AS claimed_total
           FROM claims GROUP BY policy_id) cl ON cl.policy_id = p.policy_id
LEFT JOIN (SELECT c.policy_id, SUM(s.settled_amount) AS settled_total
           FROM settlements s JOIN claims c ON c.claim_id = s.claim_id
           GROUP BY c.policy_id) st ON st.policy_id = p.policy_id;

-- Loss ratio by policy type (settled claims / premium collected)
CREATE VIEW v_loss_ratio_by_type AS
SELECT  t.type_name,
        COUNT(*)                                             AS policies,
        SUM(f.claims_count)                                  AS claims,
        ROUND(1.0 * SUM(f.claims_count) / COUNT(*), 3)             AS claim_ratio,
        SUM(f.premium_paid)                                  AS premium_collected,
        SUM(f.settled_total)                                 AS claims_settled,
        ROUND(100 * SUM(f.settled_total) / NULLIF(SUM(f.premium_paid), 0), 2) AS loss_ratio_pct
FROM v_policy_financials f
JOIN policy_types t ON t.policy_type_id = f.policy_type_id
GROUP BY t.type_name;
