"""Builds notebooks/ClaimSure_Analysis.ipynb (so the notebook source stays readable in git)."""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cells = []
def md(t): cells.append({"cell_type": "markdown", "metadata": {}, "source": t.strip("\n").splitlines(True)})
def code(t): cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                           "source": t.strip("\n").splitlines(True)})

md("""
# ClaimSure - Insurance Policy and Claims Analytics
**DBMS for Analytics Mini Project (25MSDA1S04)** - B R Sahana (26MSDSR057)

This notebook connects to the MySQL database `claimsure` using the Python **DB-API** (`mysql-connector-python`),
runs analytical SQL queries and plots loss ratios by segment.

**Before running:** load `sql/schema.sql` and `sql/data.sql` into MySQL, then set the environment variables
`DB_HOST`, `DB_USER`, `DB_PASSWORD` (defaults: localhost / root / empty).
""")

code("""
import os
import pandas as pd
import matplotlib.pyplot as plt
import mysql.connector                      # DB-API 2.0 compliant driver

CHART_DIR = os.path.join("..", "docs", "charts")
os.makedirs(CHART_DIR, exist_ok=True)
plt.rcParams.update({"figure.figsize": (8, 4.5), "axes.grid": True, "grid.alpha": 0.3})

def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database="claimsure",
    )

conn = get_connection()
cur = conn.cursor()                          # DB-API cursor
cur.execute("SELECT COUNT(*) FROM claims")
print("Connected. Claims in database:", cur.fetchone()[0])
""")

code("""
def run_query(sql, params=None):
    \"\"\"Execute a SELECT through the DB-API cursor and return a DataFrame.\"\"\"
    cur.execute(sql, params or ())
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)

def num(df, *cols):
    for c in cols:
        df[c] = pd.to_numeric(df[c])
    return df
""")

md("## 1. Table sizes")
code("""
sizes = {}
for t in ["regions", "policy_types", "agents", "customers", "policies", "premiums",
          "claims", "settlements", "claim_status_log"]:
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    sizes[t] = cur.fetchone()[0]
pd.Series(sizes, name="rows").to_frame()
""")

md("## 2. Loss ratio by policy type\nLoss ratio = settled claim amount / premium collected.")
code("""
by_type = num(run_query(\"\"\"
    SELECT t.type_name,
           COUNT(*)                AS policies,
           SUM(f.claims_count)     AS claims,
           SUM(f.premium_paid)     AS premium_collected,
           SUM(f.settled_total)    AS claims_settled
    FROM v_policy_financials f
    JOIN policy_types t ON t.policy_type_id = f.policy_type_id
    GROUP BY t.type_name
\"\"\"), "policies", "claims", "premium_collected", "claims_settled")
by_type["loss_ratio_pct"] = (100 * by_type.claims_settled / by_type.premium_collected).round(1)
by_type["claim_ratio"] = (by_type.claims / by_type.policies).round(2)
by_type = by_type.sort_values("loss_ratio_pct", ascending=False)
by_type
""")
code("""
ax = by_type.plot.bar(x="type_name", y="loss_ratio_pct", legend=False, color="#2a6f97", rot=0)
ax.axhline(100, color="crimson", ls="--", lw=1, label="Break-even (100%)")
ax.set_title("Loss ratio by policy type"); ax.set_xlabel(""); ax.set_ylabel("Loss ratio (%)")
for p in ax.patches:
    ax.annotate(f"{p.get_height():.1f}%", (p.get_x() + p.get_width() / 2, p.get_height()),
                ha="center", va="bottom", fontsize=9)
ax.legend(); plt.tight_layout()
plt.savefig(os.path.join(CHART_DIR, "loss_ratio_by_policy_type.png"), dpi=150); plt.show()
""")

md("## 3. Loss ratio by customer region (segment)")
code("""
by_region = num(run_query(\"\"\"
    SELECT r.region_name,
           COUNT(*)              AS policies,
           SUM(f.premium_paid)   AS premium_collected,
           SUM(f.settled_total)  AS claims_settled
    FROM v_policy_financials f
    JOIN customers c ON c.customer_id = f.customer_id
    JOIN regions r   ON r.region_id = c.region_id
    GROUP BY r.region_name
\"\"\"), "policies", "premium_collected", "claims_settled")
by_region["loss_ratio_pct"] = (100 * by_region.claims_settled / by_region.premium_collected).round(1)
by_region = by_region.sort_values("loss_ratio_pct", ascending=False)
by_region
""")
code("""
ax = by_region.plot.bar(x="region_name", y="loss_ratio_pct", legend=False, color="#e07a5f", rot=0)
ax.axhline(100, color="crimson", ls="--", lw=1)
ax.set_title("Loss ratio by region"); ax.set_xlabel(""); ax.set_ylabel("Loss ratio (%)")
for p in ax.patches:
    ax.annotate(f"{p.get_height():.0f}%", (p.get_x() + p.get_width() / 2, p.get_height()),
                ha="center", va="bottom", fontsize=9)
plt.tight_layout()
plt.savefig(os.path.join(CHART_DIR, "loss_ratio_by_region.png"), dpi=150); plt.show()
""")

md("## 4. Loss ratio by policy type and region (heatmap)")
code("""
seg = num(run_query(\"\"\"
    SELECT t.type_name, r.region_name,
           SUM(f.premium_paid) AS premium_collected, SUM(f.settled_total) AS claims_settled
    FROM v_policy_financials f
    JOIN policy_types t ON t.policy_type_id = f.policy_type_id
    JOIN customers c    ON c.customer_id = f.customer_id
    JOIN regions r      ON r.region_id = c.region_id
    GROUP BY t.type_name, r.region_name
\"\"\"), "premium_collected", "claims_settled")
seg["loss_ratio_pct"] = 100 * seg.claims_settled / seg.premium_collected
pivot = seg.pivot(index="type_name", columns="region_name", values="loss_ratio_pct")
fig, ax = plt.subplots(figsize=(9, 4))
im = ax.imshow(pivot.values, cmap="YlOrRd", aspect="auto")
ax.set_xticks(range(len(pivot.columns)), pivot.columns); ax.set_yticks(range(len(pivot.index)), pivot.index)
for i in range(pivot.shape[0]):
    for j in range(pivot.shape[1]):
        v = pivot.values[i, j]
        ax.text(j, i, "-" if pd.isna(v) else f"{v:.0f}", ha="center", va="center", fontsize=8)
ax.set_title("Loss ratio (%) by policy type and region"); ax.grid(False); fig.colorbar(im)
plt.tight_layout()
plt.savefig(os.path.join(CHART_DIR, "loss_ratio_heatmap.png"), dpi=150); plt.show()
""")

md("## 5. Average settlement time by policy type")
code("""
st = run_query(\"\"\"
    SELECT t.type_name, c.claim_date, s.settled_date
    FROM settlements s
    JOIN claims c       ON c.claim_id = s.claim_id
    JOIN policies p     ON p.policy_id = c.policy_id
    JOIN policy_types t ON t.policy_type_id = p.policy_type_id
\"\"\")
st["days"] = (pd.to_datetime(st.settled_date) - pd.to_datetime(st.claim_date)).dt.days
avg_days = st.groupby("type_name").days.mean().round(1).sort_values()
ax = avg_days.plot.barh(color="#81b29a")
ax.set_title("Average days from claim to settlement"); ax.set_xlabel("Days"); ax.set_ylabel("")
plt.tight_layout()
plt.savefig(os.path.join(CHART_DIR, "avg_settlement_days.png"), dpi=150); plt.show()
avg_days
""")

md("## 6. Claims by status")
code("""
status = run_query("SELECT status, COUNT(*) AS claims FROM claims GROUP BY status")
status = status.set_index("status").claims.sort_values(ascending=False)
ax = status.plot.pie(autopct="%1.0f%%", startangle=90, figsize=(5, 5), ylabel="")
ax.set_title("Claims by status"); plt.tight_layout()
plt.savefig(os.path.join(CHART_DIR, "claims_by_status.png"), dpi=150); plt.show()
""")

md("## 7. Agent performance (top 8 by premium collected)")
code("""
agents = num(run_query(\"\"\"
    SELECT a.full_name AS agent,
           SUM(f.premium_paid)  AS premium_collected,
           SUM(f.settled_total) AS claims_settled
    FROM agents a
    JOIN v_policy_financials f ON f.agent_id = a.agent_id
    GROUP BY a.agent_id, a.full_name
\"\"\"), "premium_collected", "claims_settled")
agents["loss_ratio_pct"] = (100 * agents.claims_settled / agents.premium_collected).round(1)
top = agents.sort_values("premium_collected", ascending=False).head(8)
ax = top.plot.bar(x="agent", y="premium_collected", legend=False, color="#3d405b", rot=30)
ax.set_title("Top agents by premium collected"); ax.set_xlabel(""); ax.set_ylabel("Premium (INR)")
plt.tight_layout()
plt.savefig(os.path.join(CHART_DIR, "top_agents_premium.png"), dpi=150); plt.show()
top
""")

md("## 8. Lapse rate by region")
code("""
lapse = run_query(\"\"\"
    SELECT r.region_name,
           COUNT(*) AS policies,
           SUM(CASE WHEN p.status = 'LAPSED' THEN 1 ELSE 0 END) AS lapsed
    FROM policies p
    JOIN customers c ON c.customer_id = p.customer_id
    JOIN regions r   ON r.region_id = c.region_id
    GROUP BY r.region_name
\"\"\")
lapse = num(lapse, "policies", "lapsed")
lapse["lapse_rate_pct"] = (100 * lapse.lapsed / lapse.policies).round(1)
lapse.sort_values("lapse_rate_pct", ascending=False)
""")

md("## 9. DB-API demo: parameterised query and transaction\nShows `cursor.execute` with parameters, `commit` and `rollback`.")
code("""
# Parameterised SELECT
big = run_query("SELECT claim_number, claim_type, claimed_amount, status FROM claims "
                "WHERE claimed_amount > %s ORDER BY claimed_amount DESC LIMIT 5", (300000,))
display(big)

# Transaction: change a claim status (trigger logs it), then roll back so data stays unchanged
try:
    cur.execute("SELECT claim_id FROM claims WHERE status = 'SUBMITTED' LIMIT 1")
    claim_id = cur.fetchone()[0]
    cur.execute("UPDATE claims SET status = %s WHERE claim_id = %s", ("UNDER_REVIEW", claim_id))
    cur.execute("SELECT old_status, new_status FROM claim_status_log WHERE claim_id = %s", (claim_id,))
    print("Trigger logged:", cur.fetchall())
finally:
    conn.rollback()
""")

code("""
cur.close()
conn.close()
""")

nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                   "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
out = os.path.join(ROOT, "notebooks", "ClaimSure_Analysis.ipynb")
with open(out, "w") as f:
    json.dump(nb, f, indent=1)
print("wrote", out)
