-- Server version 8.4.0
CREATE DATABASE app DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
USE app;
CREATE TABLE products (
    id bigint PRIMARY KEY,
    price decimal(12,2),
    tax decimal(12,2) GENERATED ALWAYS AS (price * 0.2) STORED,
    CONSTRAINT positive CHECK (price > 0) /*!80016 NOT ENFORCED */
);
CREATE TABLE product_summary (id bigint);
DROP TABLE IF EXISTS product_summary;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`app`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW product_summary AS SELECT id, price + tax AS total FROM products */;
