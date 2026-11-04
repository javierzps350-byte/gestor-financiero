PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    identification TEXT,
    phone TEXT,
    email TEXT,
    notes TEXT,
    billing_day INTEGER NOT NULL DEFAULT 1 CHECK (billing_day BETWEEN 1 AND 31),
    first_billing_date TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS client_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    monthly_amount_cents INTEGER NOT NULL CHECK (monthly_amount_cents > 0),
    effective_from TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT,
    UNIQUE (client_id, effective_from)
);

CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL CHECK (direction IN ('income','expense')),
    client_id INTEGER,
    counterparty TEXT NOT NULL,
    reason TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    payment_date TEXT NOT NULL,
    registered_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    payment_method TEXT NOT NULL,
    voucher_number TEXT,
    notes TEXT,
    category TEXT NOT NULL DEFAULT 'Otros',
    apply_to_monthly INTEGER NOT NULL DEFAULT 0 CHECK (apply_to_monthly IN (0,1)),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','void')),
    void_reason TEXT,
    voided_at TEXT,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS monthly_charges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    rate_id INTEGER NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    due_date TEXT NOT NULL,
    amount_due_cents INTEGER NOT NULL CHECK (amount_due_cents > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT,
    FOREIGN KEY (rate_id) REFERENCES client_rates(id) ON DELETE RESTRICT,
    UNIQUE (client_id, period_start)
);

CREATE TABLE IF NOT EXISTS payment_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movement_id INTEGER NOT NULL,
    charge_id INTEGER NOT NULL,
    amount_allocated_cents INTEGER NOT NULL CHECK (amount_allocated_cents > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (movement_id) REFERENCES movements(id) ON DELETE RESTRICT,
    FOREIGN KEY (charge_id) REFERENCES monthly_charges(id) ON DELETE RESTRICT,
    UNIQUE (movement_id, charge_id)
);

CREATE TABLE IF NOT EXISTS evidence_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movement_id INTEGER NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    mime_type TEXT,
    file_size_bytes INTEGER,
    sha256 TEXT NOT NULL,
    added_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (movement_id) REFERENCES movements(id) ON DELETE RESTRICT,
    UNIQUE (movement_id, sha256)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_movements_date ON movements(payment_date);
CREATE INDEX IF NOT EXISTS idx_movements_direction ON movements(direction);
CREATE INDEX IF NOT EXISTS idx_movements_counterparty ON movements(counterparty COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_movements_voucher ON movements(voucher_number);
CREATE INDEX IF NOT EXISTS idx_charges_client_period ON monthly_charges(client_id, period_start);
CREATE INDEX IF NOT EXISTS idx_allocations_charge ON payment_allocations(charge_id);
CREATE INDEX IF NOT EXISTS idx_evidence_movement ON evidence_files(movement_id);
