import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch
import uuid

import psycopg2
from streamlit.testing.v1 import AppTest

import auth
import auth_store
from database import get_connection


ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "Clave-de-prueba-2026!"


class PasswordTests(unittest.TestCase):
    def test_password_hashes_are_salted_and_verified(self):
        first = auth_store.hash_password(PASSWORD)
        second = auth_store.hash_password(PASSWORD)
        self.assertNotEqual(first, second)
        self.assertNotIn(PASSWORD, first)
        self.assertTrue(auth_store.verify_password(PASSWORD, first))
        self.assertFalse(auth_store.verify_password("incorrecta", first))

    def test_rejects_short_passwords_and_invalid_hashes(self):
        with self.assertRaises(ValueError):
            auth_store.hash_password("corta")
        for encoded in (None, "", "texto-plano", "pbkdf2_sha256$999999999$a$b"):
            self.assertFalse(auth_store.verify_password(PASSWORD, encoded))


class LoginFlowTests(unittest.TestCase):
    def setUp(self):
        self.user = auth_store.User(1, "operador", "Operador de prueba")
        self.authenticator = self.enterContext(patch("auth.authenticate", return_value=self.user))
        self.active_user = self.enterContext(patch("auth.get_active_user", return_value=self.user))
        self.register = self.enterContext(patch("tracker._register_new_access", return_value=True))
        self.update = self.enterContext(patch("tracker._update_last_activity"))
        self.enterContext(patch("fdb.load_api"))
        self.firebird = self.enterContext(patch("fdb.connect"))
        cursor = self.firebird.return_value.cursor.return_value
        cursor.fetchall.return_value = []
        cursor.description = [("FECHA_VIGENCIA_ENTREGA",)]
        self.app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15)

    def login(self):
        self.app.run()
        self.app.text_input[0].set_value("operador")
        self.app.text_input[1].set_value(PASSWORD)
        self.app.button[0].click().run()
        self.assertEqual(len(self.app.exception), 0)

    def test_anonymous_user_cannot_load_dashboard_or_register_activity(self):
        self.app.run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertIn("Iniciar sesión", self.app.title[0].value)
        self.firebird.assert_not_called()
        self.register.assert_not_called()
        self.assertEqual(len(self.app.sidebar.date_input), 0)

    def test_login_logout_and_second_login_rotate_tracking_session(self):
        self.login()
        self.assertIn("Control de Carga", self.app.title[0].value)
        self.assertEqual(self.app.session_state["username"], "operador")
        first_id = self.app.session_state["tracker_session_id"]
        self.assertEqual(self.register.call_args.args[1], "operador")
        self.app.run()
        self.assertEqual(self.register.call_count, 1)
        self.update.assert_called()
        self.app.sidebar.button[0].click().run()
        self.assertIn("Iniciar sesión", self.app.title[0].value)
        for key in ("auth_user_id", "username", "tracker_session_id"):
            self.assertNotIn(key, self.app.session_state)
        self.user = auth_store.User(2, "otro", "Otro usuario")
        self.authenticator.return_value = self.user
        self.active_user.return_value = self.user
        self.login()
        self.assertNotEqual(first_id, self.app.session_state["tracker_session_id"])
        self.assertEqual(self.register.call_args.args[1], "otro")

    def test_invalid_login_and_database_failure_keep_dashboard_hidden(self):
        self.authenticator.return_value = None
        self.login()
        self.assertEqual(self.app.error[0].value, auth.INVALID_LOGIN)
        self.register.assert_not_called()
        self.firebird.assert_not_called()
        self.authenticator.side_effect = psycopg2.OperationalError("secret detail")
        self.login()
        self.assertIn("No se pudo iniciar sesión", self.app.error[0].value)
        self.assertNotIn("secret detail", self.app.error[0].value)
        self.firebird.assert_not_called()

    def test_empty_form_never_authenticates(self):
        self.app.run()
        self.app.button[0].click().run()
        self.authenticator.assert_not_called()
        self.assertEqual(len(self.app.warning), 1)

    def test_expired_session_requires_login(self):
        self.login()
        self.app.session_state["auth_last_activity"] = time.time() - 1801
        self.app.run()
        self.assertIn("Iniciar sesión", self.app.title[0].value)
        self.assertEqual(len(self.app.info), 1)
        self.assertNotIn("username", self.app.session_state)

    def test_disabled_user_loses_access(self):
        self.login()
        self.active_user.return_value = None
        self.app.run()
        self.assertIn("Iniciar sesión", self.app.title[0].value)
        self.assertNotIn("auth_user_id", self.app.session_state)

    def test_session_database_error_stops_before_tracking(self):
        self.login()
        self.active_user.side_effect = psycopg2.OperationalError("secret detail")
        self.app.run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertIn("No se pudo verificar", self.app.error[0].value)
        self.assertEqual(len(self.app.title), 0)
        self.update.assert_not_called()

    def test_failed_activity_insert_is_retried(self):
        self.register.return_value = False
        self.login()
        self.assertNotIn("tracker_session_id", self.app.session_state)
        self.register.return_value = True
        self.app.run()
        self.assertEqual(self.register.call_count, 2)
        self.assertIn("tracker_session_id", self.app.session_state)


class TransactionConnection:
    """Evita commits del código probado; el test revierte toda su transacción."""

    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return self.connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def close(self):
        pass


@unittest.skipUnless(os.environ.get("RUN_DB_TESTS") == "1", "Requiere PostgreSQL configurado")
class DatabaseLoginTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_connection()
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.enterContext(patch("auth_store.get_connection", return_value=TransactionConnection(self.conn)))
        self.username = "test_" + uuid.uuid4().hex
        auth_store.create_user(self.username, "Usuario de prueba", PASSWORD)

    def test_valid_invalid_and_injection_credentials(self):
        user = auth_store.authenticate(" " + self.username.upper() + " ", PASSWORD)
        self.assertEqual(user.username, self.username)
        self.assertIsNone(auth_store.authenticate(self.username, "incorrecta"))
        self.assertIsNone(auth_store.authenticate("' OR 1=1 --", PASSWORD))
        self.assertIsNone(auth_store.authenticate("inexistente_" + self.username, PASSWORD))
        self.assertEqual(auth_store.get_active_user(user.id), user)

    def test_lockout_persists_then_expires_and_resets_counter(self):
        for _ in range(5):
            self.assertIsNone(auth_store.authenticate(self.username, "incorrecta"))
        self.assertIsNone(auth_store.authenticate(self.username, PASSWORD))
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE public.pedidos_anticipados_users
                SET locked_until = CURRENT_TIMESTAMP - INTERVAL '1 second'
                WHERE username = %s
            """, (self.username,))
        # El primer error después del bloqueo empieza una cuenta nueva.
        self.assertIsNone(auth_store.authenticate(self.username, "incorrecta"))
        self.assertIsNotNone(auth_store.authenticate(self.username, PASSWORD))
        with self.conn.cursor() as cur:
            cur.execute("SELECT failed_attempts, locked_until FROM public.pedidos_anticipados_users WHERE username = %s", (self.username,))
            self.assertEqual(cur.fetchone(), (0, None))

    def test_disabled_user_cannot_login_or_resume(self):
        user = auth_store.authenticate(self.username, PASSWORD)
        with self.conn.cursor() as cur:
            cur.execute("UPDATE public.pedidos_anticipados_users SET is_active = FALSE WHERE id = %s", (user.id,))
        self.assertIsNone(auth_store.authenticate(self.username, PASSWORD))
        self.assertIsNone(auth_store.get_active_user(user.id))


if __name__ == "__main__":
    unittest.main()
