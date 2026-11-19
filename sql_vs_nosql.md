# SQL vs NoSQL in ClaimSure

| Aspect | MySQL (relational) | MongoDB (document) |
|---|---|---|
| What we store | Customers, policies, premiums, claims, settlements - structured, related, transactional data | Claim documents with variable investigation notes, documents list and tags |
| Schema | Fixed, enforced (3NF, keys, CHECKs, ENUMs) | Flexible; each claim can carry different investigation fields |
| Relationships | Foreign keys and JOINs keep data consistent | Related data is embedded (notes inside the claim) - no JOIN needed to read a claim |
| Integrity | ACID transactions, triggers (status audit log) | Single-document atomicity; integrity must be enforced in application code |
| Analytics | Excellent for aggregates across tables: loss ratio, agent ranking, window functions | Aggregation pipeline is good for per-collection grouping (claims by type/region/outcome) |
| Changing structure | `ALTER TABLE`, migrations | Add new fields to new documents with no migration |
| Best used for | Financial truth: premiums, settlements, reporting | Semi-structured, evolving data: investigation notes, attachments, fraud flags |

**Conclusion:** use both. MySQL is the system of record for money and policy data, where consistency matters.
MongoDB complements it for unstructured investigation data that varies per claim and is read as a whole document.
