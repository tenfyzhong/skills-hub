-- Server version 8.0.36
CREATE DATABASE app DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
USE app;
CREATE TABLE users (
    id bigint NOT NULL,
    name varchar(64) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY name_key (name)
) ENGINE=InnoDB;
CREATE TABLE orders (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    amount decimal(10,2) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT positive_amount CHECK (amount > 0)
) ENGINE=InnoDB;
CREATE TABLE documents (
    id bigint PRIMARY KEY,
    body text,
    FULLTEXT KEY search_body (body)
) ENGINE=InnoDB;
