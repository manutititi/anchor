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

// VPN collections
db.createCollection("vpn_ip_pool");
db.createCollection("vpn_leases");
db.createCollection("vpn_nonces");
db.createCollection("vpn_uid_counter");

db.vpn_leases.createIndex({ uid: 1 }, { unique: true });
db.vpn_leases.createIndex({ expires_at: 1 });  // for janitor queries

// Anti-replay: unique nonce index + TTL auto-expiry after 60 s
db.vpn_nonces.createIndex({ nonce: 1 }, { unique: true });
db.vpn_nonces.createIndex({ created_at: 1 }, { expireAfterSeconds: 60 });

// Reserve uid=1 (WireGuard server) and uid=2 (linuxserver PEERS=peer1 auto-peer).
// Dynamic users start from uid=3 (10.13.13.3+).
// seq=1 → first $inc gives seq=2 → uid = 2+1 = 3.
db.vpn_uid_counter.insertOne({ _id: "vpn_uid", seq: 1 });
