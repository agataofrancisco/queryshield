-- 007: derive RLS tenant from the authenticated login, even when a view owner evaluates RLS.
-- PostgreSQL applies the view owner's row policies by default; session_user remains the
-- original login identity through view and SECURITY DEFINER execution contexts.

SET ROLE qs_app;

ALTER POLICY tenant_isolation ON qs_private.sellers
    USING (id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user))
    WITH CHECK (id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user));

ALTER POLICY tenant_isolation ON qs_private.categories
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user));

ALTER POLICY tenant_isolation ON qs_private.customers
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user));

ALTER POLICY tenant_isolation ON qs_private.products
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user));

ALTER POLICY tenant_isolation ON qs_private.orders
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user));

ALTER POLICY tenant_isolation ON qs_private.order_items
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user));

ALTER POLICY tenant_isolation ON qs_private.returns
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user));

ALTER POLICY tenant_isolation ON qs_private.payments
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user));

ALTER POLICY tenant_isolation ON qs_private.payouts
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user));

ALTER POLICY tenant_isolation ON qs_private.internal_fraud_flags
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = session_user));

RESET ROLE;
