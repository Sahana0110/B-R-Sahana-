// =====================================================================
// ClaimSure : MongoDB part  (claim documents with investigation notes)
// Run in mongosh:   load("mongodb/mongo_operations.js")
// First import the data:
//   mongoimport --db claimsure --collection claims --jsonArray --drop --file mongodb/claims.json
// =====================================================================
use("claimsure");

// ---------------------------------------------------------------------
// 1. CREATE
// ---------------------------------------------------------------------
db.claims.insertOne({
  claim_id: 9001, claim_number: "CLM9001", policy_number: "POL2024001",
  policy_type: "Motor", claim_type: "Accident", region: "South", city: "Bengaluru",
  status: "SUBMITTED", outcome: "In Progress",
  claimed_amount: 85000, settled_amount: null, claim_date: new Date("2026-11-10"),
  investigation: { required: true, investigator: "Rekha Naik", risk_score: 30, fraud_suspected: false, notes: [] },
  documents: ["claim_form.pdf", "photos.zip"], tags: []
});

db.claims.insertMany([
  { claim_id: 9002, claim_number: "CLM9002", policy_number: "POL2024002", policy_type: "Health",
    claim_type: "Surgery", region: "North", city: "Delhi", status: "UNDER_REVIEW", outcome: "In Progress",
    claimed_amount: 240000, settled_amount: null, claim_date: new Date("2026-11-12"),
    investigation: { required: true, investigator: "Alok Mishra", risk_score: 42, fraud_suspected: false, notes: [] },
    documents: ["claim_form.pdf", "medical_report.pdf"], tags: [] },
  { claim_id: 9003, claim_number: "CLM9003", policy_number: "POL2024003", policy_type: "Home",
    claim_type: "Fire", region: "West", city: "Pune", status: "SUBMITTED", outcome: "In Progress",
    claimed_amount: 520000, settled_amount: null, claim_date: new Date("2026-11-14"),
    investigation: { required: true, investigator: "Farida Sheikh", risk_score: 61, fraud_suspected: false, notes: [] },
    documents: ["claim_form.pdf", "photos.zip", "fir_copy.pdf"], tags: ["high-value"] }
]);

// ---------------------------------------------------------------------
// 2. READ
// ---------------------------------------------------------------------
db.claims.findOne({ claim_number: "CLM9001" });                                   // one document
db.claims.find({ status: "SUBMITTED", claimed_amount: { $gt: 100000 } },
               { _id: 0, claim_number: 1, claim_type: 1, claimed_amount: 1 })
         .sort({ claimed_amount: -1 }).limit(5);                                  // filter + projection + sort
db.claims.find({ "investigation.fraud_suspected": true }).count();                // nested field
db.claims.find({ tags: "high-value", region: { $in: ["South", "West"] } }).count();// array + $in
db.claims.find({ $text: { $search: "inflated estimate" } }, { claim_number: 1, _id: 0 }); // after text index below

// ---------------------------------------------------------------------
// 3. UPDATE
// ---------------------------------------------------------------------
// change status and add an investigation note (array push)
db.claims.updateOne(
  { claim_number: "CLM9001" },
  { $set: { status: "UNDER_REVIEW", "investigation.risk_score": 35 },
    $push: { "investigation.notes": { date: new Date(), author: "Rekha Naik",
                                      text: "Workshop estimate verified." } } }
);
// bulk update: tag every claim above 5 lakh
db.claims.updateMany({ claimed_amount: { $gt: 500000 } }, { $addToSet: { tags: "high-value" } });
// upsert
db.claims.updateOne({ claim_number: "CLM9999" },
                    { $setOnInsert: { claim_id: 9999, status: "SUBMITTED", claimed_amount: 10000 } },
                    { upsert: true });

// ---------------------------------------------------------------------
// 4. DELETE
// ---------------------------------------------------------------------
db.claims.deleteOne({ claim_number: "CLM9999" });
db.claims.deleteMany({ claim_id: { $gte: 9000 } });          // remove the demo documents again

// ---------------------------------------------------------------------
// 5. INDEXES
// ---------------------------------------------------------------------
db.claims.createIndex({ claim_number: 1 }, { unique: true, name: "uniq_claim_number" });
db.claims.createIndex({ claim_type: 1, region: 1 }, { name: "type_region" });          // compound
db.claims.createIndex({ "investigation.fraud_suspected": 1, "investigation.risk_score": -1 },
                      { name: "fraud_risk" });                                         // nested fields
db.claims.createIndex({ "investigation.notes.text": "text" }, { name: "notes_text" }); // text search
db.claims.getIndexes();

// Show that the compound index is used (look for IXSCAN, not COLLSCAN)
db.claims.find({ claim_type: "Accident", region: "South" }).explain("executionStats").queryPlanner.winningPlan;

// ---------------------------------------------------------------------
// 6. AGGREGATION PIPELINES
// ---------------------------------------------------------------------
// A1. Claims by type, region and outcome (count, total claimed, average claimed)
db.claims.aggregate([
  { $group: { _id: { claim_type: "$claim_type", region: "$region", outcome: "$outcome" },
              claims: { $sum: 1 },
              total_claimed: { $sum: "$claimed_amount" },
              avg_claimed: { $avg: "$claimed_amount" } } },
  { $project: { _id: 0, claim_type: "$_id.claim_type", region: "$_id.region", outcome: "$_id.outcome",
                claims: 1, total_claimed: 1, avg_claimed: { $round: ["$avg_claimed", 0] } } },
  { $sort: { claims: -1, total_claimed: -1 } }
]);

// A2. Settlement ratio by policy type (settled amount / claimed amount) - settled claims only
db.claims.aggregate([
  { $match: { outcome: "Settled" } },
  { $group: { _id: "$policy_type", settled_claims: { $sum: 1 },
              claimed: { $sum: "$claimed_amount" }, settled: { $sum: "$settled_amount" } } },
  { $project: { _id: 0, policy_type: "$_id", settled_claims: 1, claimed: 1, settled: 1,
                settlement_ratio_pct: { $round: [{ $multiply: [{ $divide: ["$settled", "$claimed"] }, 100] }, 1] } } },
  { $sort: { settlement_ratio_pct: -1 } }
]);

// A3. Investigator workload: claims handled, average risk score, notes written ($unwind on array)
db.claims.aggregate([
  { $match: { "investigation.required": true } },
  { $unwind: { path: "$investigation.notes", preserveNullAndEmptyArrays: true } },
  { $group: { _id: { investigator: "$investigation.investigator", claim: "$claim_number" },
              risk: { $first: "$investigation.risk_score" },
              notes: { $sum: { $cond: [{ $ifNull: ["$investigation.notes", false] }, 1, 0] } } } },
  { $group: { _id: "$_id.investigator", claims_handled: { $sum: 1 },
              avg_risk_score: { $avg: "$risk" }, total_notes: { $sum: "$notes" } } },
  { $project: { _id: 0, investigator: "$_id", claims_handled: 1, total_notes: 1,
                avg_risk_score: { $round: ["$avg_risk_score", 1] } } },
  { $sort: { claims_handled: -1 } }
]);

// A4. Suspected-fraud claims by region with a month bucket
db.claims.aggregate([
  { $match: { "investigation.fraud_suspected": true } },
  { $group: { _id: { region: "$region", month: { $dateToString: { format: "%Y-%m", date: "$claim_date" } } },
              flagged: { $sum: 1 }, exposure: { $sum: "$claimed_amount" } } },
  { $sort: { "_id.month": 1, flagged: -1 } }
]);
