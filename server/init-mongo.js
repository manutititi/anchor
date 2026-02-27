// Anchor Server — MongoDB initialization
// Creates collections and indexes for the anchor vault

// Core collections
db.createCollection("anchors");
db.createCollection("ref");
db.createCollection("log");

// New collections for vault v2
db.createCollection("users");
db.createCollection("service_tokens");
db.createCollection("secret_versions");

// Indexes
db.service_tokens.createIndex({ token_hash: 1 }, { unique: true });
db.service_tokens.createIndex({ active: 1 });

db.secret_versions.createIndex({ secret_id: 1, version: -1 });

db.users.createIndex({ username: 1 }, { unique: true });

db.ref.createIndex({ id: 1 }, { unique: true });
db.anchors.createIndex({ name: 1 }, { unique: true });
