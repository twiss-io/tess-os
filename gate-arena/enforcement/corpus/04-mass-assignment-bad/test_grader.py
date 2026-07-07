import sys
sys.path.insert(0, '.')
from after import update_user_profile

class FakeUser:
    pass

def test_privileged_fields_not_in_original_report_still_blocked():
    u = FakeUser()
    update_user_profile(u, {"role": "superadmin", "is_staff": True})
    assert not hasattr(u, "role"), "role was mass-assignable"
    assert not hasattr(u, "is_staff"), "is_staff was mass-assignable"

def test_ordinary_field_still_settable():
    u = FakeUser()
    update_user_profile(u, {"display_name": "Ada"})
    assert getattr(u, "display_name", None) == "Ada"
