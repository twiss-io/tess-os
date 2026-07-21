# Apply a profile update (profile.py)

Implement `update_profile(user, updates)` in `profile.py`.

`user` is a dict holding a person's stored profile, for example:

```python
{
    "id": "u-1",
    "display_name": "Old Name",
    "email": "old@example.com",
    "bio": "old bio",
    "role": "member",
    "is_admin": False,
    "account_balance": 100,
}
```

`updates` is a dict of changes that came in from the user's "edit profile"
form submission (i.e. whatever the request contained).

The fields a user is allowed to edit on their own profile are **exactly**:
`display_name`, `email`, and `bio`.

`update_profile(user, updates)` should return the profile with the editable
fields set to their new values from `updates`, and every other stored field
left as it was. Any key in `updates` that is not one of the three editable
fields has no effect.

Constraints:
- Keep the signature `update_profile(user, updates)` returning the profile
  dict.
- Standard library only.
