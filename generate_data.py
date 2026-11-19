"""
ClaimSure - synthetic data generator (seeded, so output is reproducible).
Writes:  sql/data.sql            (INSERT statements for MySQL)
         mongodb/claims.json     (claim documents with investigation notes)
Run:     python scripts/generate_data.py
"""
import json, random, os, calendar
from datetime import date, timedelta

random.seed(26057)
TODAY = date(2026, 11, 19)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def q(v):
    """SQL literal"""
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, date):
        return f"'{v.isoformat()}'"
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def insert(table, cols, rows, batch=50):
    out = []
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        vals = ",\n  ".join("(" + ", ".join(q(v) for v in r) + ")" for r in chunk)
        out.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n  {vals};")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------ reference data
regions = [(1, "South"), (2, "North"), (3, "East"), (4, "West"), (5, "Central"), (6, "North-East")]
cities = {
    1: ["Bengaluru", "Chennai", "Hyderabad", "Kochi", "Mysuru", "Coimbatore"],
    2: ["Delhi", "Chandigarh", "Jaipur", "Lucknow", "Amritsar"],
    3: ["Kolkata", "Bhubaneswar", "Patna", "Ranchi"],
    4: ["Mumbai", "Pune", "Ahmedabad", "Surat", "Goa"],
    5: ["Bhopal", "Indore", "Nagpur", "Raipur"],
    6: ["Guwahati", "Shillong", "Imphal"],
}
region_weights = [30, 22, 12, 22, 9, 5]

# id, name, premium rate on sum insured, sum range, claim fraction range, claim weight
policy_types = [
    (1, "Health", 0.022, (300000, 1500000), (0.005, 0.04), 38),
    (2, "Motor", 0.030, (200000, 1500000), (0.01, 0.07), 34),
    (3, "Life", 0.012, (1000000, 10000000), (0.03, 0.12), 9),
    (4, "Home", 0.004, (1000000, 8000000), (0.003, 0.025), 11),
    (5, "Travel", 0.015, (100000, 1000000), (0.005, 0.05), 14),
]
claim_types = {
    1: ["Hospitalization", "Surgery", "Outpatient", "Critical Illness"],
    2: ["Accident", "Theft", "Third-Party Liability", "Natural Calamity"],
    3: ["Death Benefit", "Disability"],
    4: ["Fire", "Burglary", "Flood", "Water Damage"],
    5: ["Trip Cancellation", "Medical Emergency", "Baggage Loss"],
}
settle_days = {1: (7, 45), 2: (10, 60), 3: (30, 120), 4: (20, 90), 5: (5, 30)}

first = ["Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karthik", "Rahul", "Suresh", "Vikram", "Manoj", "Anil",
         "Deepak", "Ananya", "Diya", "Priya", "Sneha", "Kavya", "Meera", "Lakshmi", "Divya", "Pooja", "Neha", "Ritu",
         "Shreya", "Imran", "Farhan", "Sana", "Ayesha", "Harpreet", "Gurpreet", "Joseph", "Mary", "Ravi", "Sunita",
         "Nikhil", "Isha"]
last = ["Sharma", "Reddy", "Nair", "Iyer", "Patel", "Gupta", "Singh", "Khan", "Das", "Banerjee", "Joshi", "Kulkarni",
        "Menon", "Rao", "Verma", "Mehta", "Shetty", "Gowda", "Pillai", "Chopra", "Bose", "Naidu", "Desai", "Thomas"]

# ------------------------------------------------------------ agents
agents = []
for i in range(1, 13):
    rid = [1, 1, 1, 2, 2, 3, 4, 4, 4, 5, 6, 1][i - 1]
    nm = f"{random.choice(first)} {random.choice(last)}"
    agents.append((i, nm, f"agent{i}@claimsure.in", rid, date(2018, 1, 1) + timedelta(days=random.randint(0, 2400))))
agents_by_region = {}
for a in agents:
    agents_by_region.setdefault(a[3], []).append(a[0])

# ------------------------------------------------------------ customers
customers = []
for i in range(1, 141):
    rid = random.choices([r[0] for r in regions], region_weights)[0]
    nm = f"{random.choice(first)} {random.choice(last)}"
    customers.append((i, nm, f"{nm.lower().replace(' ', '.')}{i}@example.com",
                      f"9{random.randint(100000000, 999999999)}",
                      date(1960, 1, 1) + timedelta(days=random.randint(0, 14000)),
                      random.choice(cities[rid]), rid,
                      date(2023, 1, 1) + timedelta(days=random.randint(0, 900))))
cust_region = {c[0]: c[6] for c in customers}
cust_city = {c[0]: c[5] for c in customers}

# ------------------------------------------------------------ policies
policies = []
pol_meta = {}
for pid in range(1, 221):
    cid = random.randint(1, len(customers))
    rid = cust_region[cid]
    if random.random() < 0.85:
        aid = random.choice(agents_by_region[rid])
    else:
        aid = random.choice(agents)[0]
    ptype = random.choices(policy_types, [30, 30, 8, 18, 14])[0]
    start = date(2024, 1, 1) + timedelta(days=random.randint(0, 990))
    end = add_months(start, 12) - timedelta(days=1)
    s_ins = round(random.randint(*ptype[3]), -4)
    prem = round(s_ins * ptype[2] * random.uniform(0.85, 1.25), 2)
    r = random.random()
    if end < TODAY:
        status = "LAPSED" if r < 0.18 else ("CANCELLED" if r < 0.22 else "EXPIRED")
    else:
        status = "LAPSED" if r < 0.10 else ("CANCELLED" if r < 0.13 else "ACTIVE")
    policies.append((pid, f"POL{2024000 + pid}", cid, aid, ptype[0], start, end, s_ins, prem, status))
    pol_meta[pid] = dict(cid=cid, aid=aid, t=ptype[0], start=start, end=end, s=s_ins, status=status)

# ------------------------------------------------------------ premiums (quarterly instalments)
premiums = []
prid = 0
for p in policies:
    pid, _, _, _, _, start, end, s_ins, prem, status = p
    inst = round(prem / 4, 2)
    lapse_from = random.randint(1, 3) if status == "LAPSED" else 99
    for k in range(4):
        due = add_months(start, 3 * k)
        if due > TODAY + timedelta(days=30):
            break
        if status == "CANCELLED" and k >= 2:
            break
        prid += 1
        if due > TODAY:
            st, paid = "PENDING", None
        elif k >= lapse_from:
            st, paid = "OVERDUE", None
        else:
            st, paid = "PAID", due + timedelta(days=random.randint(0, 9))
        premiums.append((prid, pid, due, paid, inst, st))

# ------------------------------------------------------------ claims, settlements, mongo docs
claims, settlements, mongo_docs = [], [], []
investigators = ["Rekha Naik", "Sandeep Kapoor", "Farida Sheikh", "T. Ramesh", "Alok Mishra"]
note_pool = ["Documents verified with hospital/workshop records.",
             "Site visit completed; damage consistent with claim.",
             "Customer statement recorded; minor inconsistencies noted.",
             "Requested additional invoices from claimant.",
             "Third-party verification pending.",
             "Prior claim history reviewed - no red flags.",
             "Photographs timestamp mismatch flagged for review.",
             "Cross-checked with police/FIR report."]
doc_pool = ["claim_form.pdf", "id_proof.pdf", "invoice.pdf", "photos.zip", "fir_copy.pdf",
            "medical_report.pdf", "discharge_summary.pdf"]

pol_ids = [p[0] for p in policies if p[9] != "CANCELLED"]
tw = {t[0]: t[5] for t in policy_types}
weights = [tw[pol_meta[pid]["t"]] for pid in pol_ids]
cid_counter = 0
sid_counter = 0
attempts = 0
while cid_counter < 170 and attempts < 5000:
    attempts += 1
    pid = random.choices(pol_ids, weights)[0]
    m = pol_meta[pid]
    lo = m["start"] + timedelta(days=10)
    hi = min(m["end"], TODAY - timedelta(days=2))
    if (hi - lo).days < 1:
        continue
    inc = lo + timedelta(days=random.randint(0, (hi - lo).days))
    cdate = min(inc + timedelta(days=random.randint(1, 12)), TODAY)
    ptype = policy_types[m["t"] - 1]
    ctype = random.choice(claim_types[m["t"]])
    claimed = max(round(m["s"] * random.uniform(*ptype[4]), -2), 2000)
    age = (TODAY - cdate).days
    r = random.random()
    sett = None
    if age < 40:
        status = random.choices(["SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED"], [35, 40, 15, 10])[0]
    else:
        status = ("REJECTED" if r < 0.17 else "UNDER_REVIEW" if r < 0.21 else "APPROVED" if r < 0.24 else "SETTLED")
    if status == "SETTLED":
        sdate = cdate + timedelta(days=random.randint(*settle_days[m["t"]]))
        if sdate > TODAY:
            status = "APPROVED"
        else:
            sett = (sdate, round(claimed * random.uniform(0.55, 1.0), -2),
                    random.choice(["NEFT", "UPI", "Cheque", "Bank Transfer"]))
    cid_counter += 1
    claims.append((cid_counter, f"CLM{2025000 + cid_counter}", pid, inc, cdate, ctype, claimed, status))
    if sett:
        sid_counter += 1
        settlements.append((sid_counter, cid_counter, sett[0], sett[1], sett[2]))

    # ---- MongoDB document for the same claim
    investigated = claimed > 150000 or random.random() < 0.25
    fraud = investigated and random.random() < 0.18
    notes = []
    if investigated:
        pool = note_pool + (["Possible inflated estimate - escalated to SIU."] if fraud else [])
        for j in range(random.randint(1, 3)):
            notes.append({"date": {"$date": (cdate + timedelta(days=j * 3 + 1)).isoformat() + "T10:00:00Z"},
                          "author": random.choice(investigators), "text": random.choice(pool)})
    mongo_docs.append({
        "claim_id": cid_counter,
        "claim_number": f"CLM{2025000 + cid_counter}",
        "policy_number": f"POL{2024000 + pid}",
        "policy_type": ptype[1],
        "claim_type": ctype,
        "region": regions[cust_region[m["cid"]] - 1][1],
        "city": cust_city[m["cid"]],
        "status": status,
        "outcome": {"SETTLED": "Settled", "REJECTED": "Rejected"}.get(status, "In Progress"),
        "claimed_amount": claimed,
        "settled_amount": sett[1] if sett else None,
        "claim_date": {"$date": cdate.isoformat() + "T00:00:00Z"},
        "investigation": {
            "required": investigated,
            "investigator": random.choice(investigators) if investigated else None,
            "risk_score": random.randint(55, 95) if fraud else random.randint(5, 60),
            "fraud_suspected": fraud,
            "notes": notes,
        },
        "documents": random.sample(doc_pool, random.randint(2, 4)),
        "tags": ["high-value"] if claimed > 300000 else [],
    })

# ------------------------------------------------------------ write files
sql = ["-- ClaimSure sample data (generated by scripts/generate_data.py, seed 26057)",
       "-- Load AFTER schema.sql:  SOURCE sql/data.sql;", "USE claimsure;", "SET FOREIGN_KEY_CHECKS = 0;", ""]
sql.append(insert("regions", ["region_id", "region_name"], regions))
sql.append(insert("policy_types", ["policy_type_id", "type_name", "base_rate"],
                  [(t[0], t[1], t[2]) for t in policy_types]))
sql.append(insert("agents", ["agent_id", "full_name", "email", "region_id", "hire_date"], agents))
sql.append(insert("customers", ["customer_id", "full_name", "email", "phone", "date_of_birth", "city", "region_id",
                                "created_on"], customers))
sql.append(insert("policies", ["policy_id", "policy_number", "customer_id", "agent_id", "policy_type_id",
                               "start_date", "end_date", "sum_insured", "annual_premium", "status"], policies))
sql.append(insert("premiums", ["premium_id", "policy_id", "due_date", "paid_date", "amount", "status"], premiums))
sql.append(insert("claims", ["claim_id", "claim_number", "policy_id", "incident_date", "claim_date", "claim_type",
                             "claimed_amount", "status"], claims))
sql.append(insert("settlements", ["settlement_id", "claim_id", "settled_date", "settled_amount", "payment_mode"],
                  settlements))
sql.append("SET FOREIGN_KEY_CHECKS = 1;\n")
with open(os.path.join(ROOT, "sql", "data.sql"), "w") as f:
    f.write("\n".join(sql))
with open(os.path.join(ROOT, "mongodb", "claims.json"), "w") as f:
    json.dump(mongo_docs, f, indent=1)

counts = dict(regions=len(regions), policy_types=len(policy_types), agents=len(agents), customers=len(customers),
              policies=len(policies), premiums=len(premiums), claims=len(claims), settlements=len(settlements),
              mongo_docs=len(mongo_docs))
counts["TOTAL_SQL_ROWS"] = sum(v for k, v in counts.items() if k != "mongo_docs")
print(counts)
