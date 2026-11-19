-- =====================================================================
-- ClaimSure : analytical queries   (MySQL 8.0+)
-- Run after schema.sql and data.sql:   mysql -u root -p claimsure < sql/queries.sql
-- =====================================================================
USE claimsure;

-- ---------------------------------------------------------------------
-- Q1. Claim ratio and loss ratio by policy type  (uses the view)
--     claim_ratio    = claims filed per policy
--     loss_ratio_pct = settled amount / premium collected * 100
-- ---------------------------------------------------------------------
SELECT * FROM v_loss_ratio_by_type ORDER BY loss_ratio_pct DESC;

-- ---------------------------------------------------------------------
-- Q2. Average settlement time (days from claim date to settlement)
-- ---------------------------------------------------------------------
-- 2a. overall
SELECT ROUND(AVG(DATEDIFF(s.settled_date, c.claim_date)), 1) AS avg_days_to_settle,
       MIN(DATEDIFF(s.settled_date, c.claim_date))           AS fastest_days,
       MAX(DATEDIFF(s.settled_date, c.claim_date))           AS slowest_days
FROM claims c
JOIN settlements s ON s.claim_id = c.claim_id;

-- 2b. by policy type
SELECT t.type_name,
       COUNT(*)                                              AS settled_claims,
       ROUND(AVG(DATEDIFF(s.settled_date, c.claim_date)), 1) AS avg_days_to_settle
FROM settlements s
JOIN claims c        ON c.claim_id = s.claim_id
JOIN policies p      ON p.policy_id = c.policy_id
JOIN policy_types t  ON t.policy_type_id = p.policy_type_id
GROUP BY t.type_name
ORDER BY avg_days_to_settle;

-- ---------------------------------------------------------------------
-- Q3. Agent performance with ranking (window function)
-- ---------------------------------------------------------------------
SELECT a.agent_id,
       a.full_name                                   AS agent,
       r.region_name                                 AS region,
       COUNT(f.policy_id)                            AS policies_sold,
       ROUND(SUM(f.premium_paid), 2)                 AS premium_collected,
       SUM(f.claims_count)                           AS claims,
       ROUND(100 * SUM(f.settled_total) / NULLIF(SUM(f.premium_paid), 0), 2) AS loss_ratio_pct,
       RANK() OVER (ORDER BY SUM(f.premium_paid) DESC) AS premium_rank
FROM agents a
JOIN regions r               ON r.region_id = a.region_id
LEFT JOIN v_policy_financials f ON f.agent_id = a.agent_id
GROUP BY a.agent_id, a.full_name, r.region_name
ORDER BY premium_rank;

-- ---------------------------------------------------------------------
-- Q4. Lapsed policies with their overdue premium amount
-- ---------------------------------------------------------------------
SELECT p.policy_number,
       cu.full_name                      AS customer,
       t.type_name                       AS policy_type,
       a.full_name                       AS agent,
       COUNT(pr.premium_id)              AS overdue_instalments,
       SUM(pr.amount)                    AS overdue_amount
FROM policies p
JOIN customers cu    ON cu.customer_id = p.customer_id
JOIN policy_types t  ON t.policy_type_id = p.policy_type_id
JOIN agents a        ON a.agent_id = p.agent_id
LEFT JOIN premiums pr ON pr.policy_id = p.policy_id AND pr.status = 'OVERDUE'
WHERE p.status = 'LAPSED'
GROUP BY p.policy_id, p.policy_number, cu.full_name, t.type_name, a.full_name
ORDER BY overdue_amount DESC;

-- ---------------------------------------------------------------------
-- Q5. Lapse rate by region (share of policies that lapsed)
-- ---------------------------------------------------------------------
SELECT r.region_name,
       COUNT(*)                                             AS policies,
       SUM(p.status = 'LAPSED')                             AS lapsed,
       ROUND(100 * SUM(p.status = 'LAPSED') / COUNT(*), 1)  AS lapse_rate_pct
FROM policies p
JOIN customers c ON c.customer_id = p.customer_id
JOIN regions r   ON r.region_id = c.region_id
GROUP BY r.region_name
ORDER BY lapse_rate_pct DESC;

-- ---------------------------------------------------------------------
-- Q6. Claims by status and type, with total claimed amount
-- ---------------------------------------------------------------------
SELECT claim_type, status, COUNT(*) AS claims, SUM(claimed_amount) AS total_claimed
FROM claims
GROUP BY claim_type, status
ORDER BY claim_type, status;

-- ---------------------------------------------------------------------
-- Q7. Customers with more than one claim (subquery + HAVING)
-- ---------------------------------------------------------------------
SELECT cu.customer_id, cu.full_name, cu.city, COUNT(c.claim_id) AS claims_filed,
       SUM(c.claimed_amount) AS total_claimed
FROM customers cu
JOIN policies p ON p.customer_id = cu.customer_id
JOIN claims c   ON c.policy_id = p.policy_id
GROUP BY cu.customer_id, cu.full_name, cu.city
HAVING COUNT(c.claim_id) > 1
ORDER BY claims_filed DESC, total_claimed DESC;

-- ---------------------------------------------------------------------
-- Q8. Monthly premium collection with running total (window function)
-- ---------------------------------------------------------------------
SELECT month_start, collected,
       SUM(collected) OVER (ORDER BY month_start) AS running_total
FROM (
    SELECT DATE_FORMAT(paid_date, '%Y-%m-01') AS month_start, SUM(amount) AS collected
    FROM premiums
    WHERE status = 'PAID'
    GROUP BY DATE_FORMAT(paid_date, '%Y-%m-01')
) m
ORDER BY month_start;

-- ---------------------------------------------------------------------
-- Q9. TRIGGER DEMO: status changes are logged automatically
-- ---------------------------------------------------------------------
-- pick an open claim and remember its id in a session variable
SELECT claim_id INTO @cid FROM claims WHERE status = 'SUBMITTED' LIMIT 1;
SELECT claim_id, claim_number, status FROM claims WHERE claim_id = @cid;

-- move it through the workflow
UPDATE claims SET status = 'UNDER_REVIEW' WHERE claim_id = @cid AND status = 'SUBMITTED';
UPDATE claims SET status = 'APPROVED'     WHERE claim_id = @cid AND status = 'UNDER_REVIEW';

-- inserting a settlement fires trg_settlement_marks_claim -> claim becomes SETTLED -> logged too
INSERT INTO settlements (claim_id, settled_date, settled_amount, payment_mode)
SELECT claim_id, CURRENT_DATE, ROUND(claimed_amount * 0.9, 2), 'UPI'
FROM claims WHERE claim_id = @cid;

SELECT * FROM claim_status_log WHERE claim_id = @cid ORDER BY log_id;   -- expect 3 rows

-- ---------------------------------------------------------------------
-- Q10. Top 5 high-value open claims (pending decision)
-- ---------------------------------------------------------------------
SELECT c.claim_number, t.type_name, c.claim_type, c.claimed_amount, c.status,
       DATEDIFF(CURRENT_DATE, c.claim_date) AS days_open
FROM claims c
JOIN policies p     ON p.policy_id = c.policy_id
JOIN policy_types t ON t.policy_type_id = p.policy_type_id
WHERE c.status IN ('SUBMITTED', 'UNDER_REVIEW', 'APPROVED')
ORDER BY c.claimed_amount DESC
LIMIT 5;

-- =====================================================================
-- DML DEMO (required by the problem statement): issue a policy, record
-- premium payments, update a claim.  Wrapped in a transaction and rolled
-- back at the end so the sample data stays unchanged.
-- =====================================================================
START TRANSACTION;

-- D1. Issue a new Health policy for customer 1 sold by agent 1
INSERT INTO policies (policy_number, customer_id, agent_id, policy_type_id,
                      start_date, end_date, sum_insured, annual_premium, status)
VALUES ('POL2026999', 1, 1, 1, '2026-11-20', '2027-11-19', 500000.00, 11000.00, 'ACTIVE');
SET @new_pid = LAST_INSERT_ID();

-- D2. Create its quarterly premium schedule
INSERT INTO premiums (policy_id, due_date, amount, status) VALUES
  (@new_pid, '2026-11-20', 2750.00, 'PENDING'),
  (@new_pid, '2027-02-20', 2750.00, 'PENDING'),
  (@new_pid, '2027-05-20', 2750.00, 'PENDING'),
  (@new_pid, '2027-08-20', 2750.00, 'PENDING');

-- D3. Customer pays the first instalment
UPDATE premiums
   SET paid_date = '2026-11-20', status = 'PAID'
 WHERE policy_id = @new_pid AND due_date = '2026-11-20';

-- D4. Mark policies with 2+ overdue instalments as LAPSED
UPDATE policies p
   SET p.status = 'LAPSED'
 WHERE p.status = 'ACTIVE'
   AND (SELECT COUNT(*) FROM premiums pr WHERE pr.policy_id = p.policy_id AND pr.status = 'OVERDUE') >= 2;

-- D5. Claim update: reject a claim under review (trigger logs the change)
UPDATE claims SET status = 'REJECTED'
 WHERE claim_id = (SELECT claim_id FROM (SELECT claim_id FROM claims WHERE status = 'UNDER_REVIEW' LIMIT 1) x);

SELECT * FROM premiums WHERE policy_id = @new_pid;
ROLLBACK;
