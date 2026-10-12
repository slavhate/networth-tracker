import re
from datetime import timezone

import two_factor as tf
from totp_helpers import NOW, NOW_STEP, SECRET, code_for


def test_verify_totp_returns_current_step_for_naive_utc_now():
    # Pins the absolute step: fails under TZ=Asia/Kolkata if naive `now` reaches pyotp unconverted.
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP), None, NOW) == NOW_STEP


def test_verify_totp_treats_aware_and_naive_utc_the_same():
    aware = NOW.replace(tzinfo=timezone.utc)
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP), None, aware) == NOW_STEP


def test_verify_totp_accepts_one_step_of_clock_drift():
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP - 1), None, NOW) == NOW_STEP - 1
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP + 1), None, NOW) == NOW_STEP + 1


def test_verify_totp_rejects_two_steps_of_drift():
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP - 2), None, NOW) is None
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP + 2), None, NOW) is None


def test_verify_totp_rejects_replayed_or_older_steps():
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP), NOW_STEP, NOW) is None
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP - 1), NOW_STEP, NOW) is None
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP + 1), NOW_STEP, NOW) == NOW_STEP + 1


def test_verify_totp_ignores_spaces_and_dashes():
    code = code_for(SECRET, NOW_STEP)
    assert tf.verify_totp(SECRET, f" {code[:3]} {code[3:]} ", None, NOW) == NOW_STEP
    assert tf.verify_totp(SECRET, f"{code[:3]}-{code[3:]}", None, NOW) == NOW_STEP


def test_verify_totp_rejects_malformed_codes_without_raising():
    for bad in ["", "12345", "1234567", "abcdef", "١٢٣٤٥٦", "12 34 5"]:
        assert tf.verify_totp(SECRET, bad, None, NOW) is None


def test_provisioning_uri_names_issuer_user_and_secret():
    uri = tf.provisioning_uri(SECRET, "alice")
    assert uri.startswith("otpauth://totp/")
    assert "issuer=NetWorth%20Tracker" in uri
    assert "alice" in uri
    assert f"secret={SECRET}" in uri


def test_generate_secret_is_base32_and_unique():
    a, b = tf.generate_secret(), tf.generate_secret()
    assert re.fullmatch(r"[A-Z2-7]{32}", a)
    assert a != b


def test_generate_backup_codes_format_and_uniqueness():
    codes = tf.generate_backup_codes()
    assert len(codes) == 10
    assert len(set(codes)) == 10
    for code in codes:
        assert re.fullmatch(r"[a-z2-7]{4}-[a-z2-7]{4}", code)


def test_hash_backup_code_ignores_case_dashes_and_spaces():
    expected = tf.hash_backup_code("abcd-efgh")
    assert tf.hash_backup_code("ABCDEFGH") == expected
    assert tf.hash_backup_code(" abcd efgh ") == expected


def test_consume_backup_code_removes_only_the_used_code():
    codes = tf.generate_backup_codes()
    hashes = [tf.hash_backup_code(c) for c in codes]
    remaining = tf.consume_backup_code(hashes, codes[3].upper().replace("-", ""))
    assert remaining == hashes[:3] + hashes[4:]
    assert tf.consume_backup_code(remaining, codes[3]) is None


def test_consume_backup_code_rejects_unknown_code():
    hashes = [tf.hash_backup_code(c) for c in tf.generate_backup_codes()]
    assert tf.consume_backup_code(hashes, "zzzz-zzzz") is None
