-- =========================================================================
-- STRIDE POST-RESTORATION DATA INTEGRITY VERIFICATION SUITE
-- Target Database: Invoked via psql -d "${RESTORE_DB}" -f verify_integrity.sql
-- =========================================================================

-- 1. Verify Django Migration State
SELECT app, name, applied 
FROM django_migrations 
ORDER BY applied DESC 
LIMIT 10;

-- 2. Check Core Table Row Counts
SELECT 'accounts_user' AS tbl, COUNT(*) FROM accounts_user
UNION ALL
SELECT 'orders_order', COUNT(*) FROM orders_order
UNION ALL
SELECT 'orders_orderrequirement', COUNT(*) FROM orders_orderrequirement
UNION ALL
SELECT 'payments_payment', COUNT(*) FROM payments_payment
UNION ALL
SELECT 'cards_card', COUNT(*) FROM cards_card
UNION ALL
SELECT 'profiles_profile', COUNT(*) FROM profiles_profile
UNION ALL
SELECT 'core_adminauditlog', COUNT(*) FROM core_adminauditlog
UNION ALL
SELECT 'core_mediacleanuptask', COUNT(*) FROM core_mediacleanuptask;

-- 3. Check Payment-to-Order Referential Integrity
-- (Every payment record must link to an existing order in orders_order)
SELECT p.id, p.reference, p.order_id, p.status, p.amount
FROM payments_payment p 
LEFT JOIN orders_order o ON p.order_id = o.id 
WHERE o.id IS NULL;
-- Expected output: 0 rows

-- 4. Check Order-to-Payment Status & Amount Consistency
-- NOTE: An order may have multiple payment records (e.g. failed/abandoned attempts).
-- We ONLY compare orders marked 'paid' against successful payments ('success').
SELECT o.order_number, o.amount AS order_amount, p.amount AS payment_amount, p.reference, p.status
FROM orders_order o
JOIN payments_payment p ON p.order_id = o.id
WHERE o.payment_status = 'paid' 
  AND p.status = 'success' 
  AND o.amount != p.amount;
-- Expected output: 0 rows

-- 5. Check for Multiple Successful Payments on a Single Order (Double Charge Anomaly)
SELECT order_id, COUNT(*) AS successful_payment_count
FROM payments_payment
WHERE status = 'success'
GROUP BY order_id
HAVING COUNT(*) > 1;
-- Expected output: 0 rows

-- 6. Check Card-to-Profile Assignment Integrity
-- In Card model: field is `profile_id` (ForeignKey to Profile, nullable)
SELECT c.card_code, c.profile_id, c.status 
FROM cards_card c 
LEFT JOIN profiles_profile pr ON c.profile_id = pr.id 
WHERE c.profile_id IS NOT NULL AND pr.id IS NULL;
-- Expected output: 0 rows

-- 7. Check Active Cards have Valid User and Profile Links
SELECT c.card_code, c.status, c.user_id, c.profile_id
FROM cards_card c
WHERE c.status = 'ACTIVE' AND (c.user_id IS NULL OR c.profile_id IS NULL);
-- Expected output: 0 rows

-- 8. Check Order Requirements 1-to-1 Integrity
-- (Cardinality: OneToOneField; orphan records must be 0)
SELECT req.id, req.order_id
FROM orders_orderrequirement req
LEFT JOIN orders_order o ON req.order_id = o.id
WHERE o.id IS NULL;
-- Expected output: 0 rows
