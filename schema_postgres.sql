DROP TABLE IF EXISTS winners;
DROP TABLE IF EXISTS invoice_items;
DROP TABLE IF EXISTS invoices;
DROP TABLE IF EXISTS raffles;
DROP TABLE IF EXISTS clients;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL, -- 'admin' or 'seller'
    name TEXT,
    phone TEXT,
    province TEXT,
    commission_percentage REAL,
    join_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    last_name TEXT,
    phone TEXT,
    address TEXT,
    seller_id INTEGER NOT NULL,
    join_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (seller_id) REFERENCES users (id)
);

CREATE TABLE raffles (
    id SERIAL PRIMARY KEY,
    raffle_date TIMESTAMP NOT NULL,
    first_prize TEXT,
    second_prize TEXT,
    third_prize TEXT,
    results_entered BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    raffle_id INTEGER NOT NULL,
    client_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    creation_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount REAL NOT NULL,
    FOREIGN KEY (raffle_id) REFERENCES raffles (id),
    FOREIGN KEY (client_id) REFERENCES clients (id),
    FOREIGN KEY (seller_id) REFERENCES users (id)
);

CREATE TABLE invoice_items (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER NOT NULL,
    number TEXT NOT NULL, -- 2 or 4 digits
    item_type TEXT NOT NULL, -- 'billete' or 'chance'
    quantity INTEGER NOT NULL,
    price_per_unit REAL NOT NULL,
    sub_total REAL NOT NULL,
    FOREIGN KEY (invoice_id) REFERENCES invoices (id)
);

CREATE TABLE winners (
    id SERIAL PRIMARY KEY,
    raffle_id INTEGER NOT NULL,
    invoice_id INTEGER NOT NULL,
    client_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    winning_number TEXT NOT NULL,
    prize_type TEXT NOT NULL,
    amount_won REAL NOT NULL,
    quantity INTEGER NOT NULL,
    total_payout REAL NOT NULL,
    FOREIGN KEY (raffle_id) REFERENCES raffles (id),
    FOREIGN KEY (invoice_id) REFERENCES invoices (id),
    FOREIGN KEY (client_id) REFERENCES clients (id),
    FOREIGN KEY (seller_id) REFERENCES users (id)
);