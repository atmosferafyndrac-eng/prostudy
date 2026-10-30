"""Run: python -m unittest discover -s tests -v"""
import unittest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
import server

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.valid={
            'name':'Марія','messenger':'Telegram','contact':'@client123','service':'Курсова робота',
            'topic':'Маркетинг','details':'Редагування розділу',
            'deadline':(date.today()+timedelta(days=3)).isoformat(),
            'website':''
        }
    def test_accepts_valid_order(self):
        x=server.validate_order(self.valid)
        self.assertEqual(x['service'],'Курсова робота')
        self.assertNotIn('consent',x)
    def test_accepts_order_without_checkbox(self):
        self.assertEqual(server.validate_order(self.valid)['name'],'Марія')
    def test_rejects_bad_service(self):
        with self.assertRaises(ValueError):
            server.validate_order({**self.valid,'service':'Довільний тип'})
    def test_rejects_past_deadline(self):
        with self.assertRaises(ValueError):
            server.validate_order({**self.valid,'deadline':'2020-01-01'})
    def test_viber_phone(self):
        x=server.validate_order({**self.valid,'messenger':'Viber','contact':'+380 99 123 45 67'})
        self.assertEqual(x['messenger'],'Viber')
    def test_whatsapp_phone(self):
        x=server.validate_order({**self.valid,'messenger':'WhatsApp','contact':'+380991234567'})
        self.assertEqual(x['messenger'],'WhatsApp')
    def test_invalid_telegram_nick(self):
        with self.assertRaises(ValueError):
            server.validate_order({**self.valid,'contact':'+380991234567'})
    def test_invalid_phone_for_messenger(self):
        with self.assertRaises(ValueError):
            server.validate_order({**self.valid,'messenger':'Viber','contact':'@client123'})
    def test_invalid_messenger(self):
        with self.assertRaises(ValueError):
            server.validate_order({**self.valid,'messenger':'Email'})
    def test_honeypot(self):
        self.assertIsNone(server.validate_order({**self.valid,'website':'spambot'}))
    def test_limit_long_fields(self):
        with self.assertRaises(ValueError):
            server.validate_order({**self.valid,'details':'x'*3001})
    def test_telegram_skipped_without_credentials(self):
        with patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'','TELEGRAM_CHAT_ID':''}):
            self.assertEqual(server.telegram_notify({'id':1}),'skipped')

if __name__=='__main__': unittest.main()
