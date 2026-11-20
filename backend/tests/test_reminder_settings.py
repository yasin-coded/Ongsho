import pytest
from django.contrib.auth import get_user_model

from accounts.validators import format_reminder_days, parse_reminder_days
from tests.test_me_part_d import STRONG, assert_error_shape, client_for

User = get_user_model()


@pytest.mark.django_db
class TestReminderSettingsDays:
    def test_get_defaults(self):
        user = User.objects.create_user(
            email="rem-def@example.com", password=STRONG, name="Rem", email_verified=True
        )
        assert client_for(user).get("/api/reminders/settings/").json() == {
            "days_before": [7, 1],
            "email": True,
        }

    def test_patch_days_and_email(self):
        user = User.objects.create_user(
            email="rem2@example.com", password=STRONG, name="Rem2", email_verified=True
        )
        client = client_for(user)
        response = client.patch(
            "/api/reminders/settings/", {"days_before": [3, 1], "email": False}, format="json"
        )
        assert response.status_code == 200
        assert response.json() == {"days_before": [3, 1], "email": False}
        user.refresh_from_db()
        assert user.reminder_days == "3,1"
        assert user.email_reminders is False

    def test_patch_email_only(self):
        user = User.objects.create_user(
            email="rem-email@example.com", password=STRONG, name="Rem", email_verified=True
        )
        client = client_for(user)
        response = client.patch("/api/reminders/settings/", {"email": False}, format="json")
        assert response.status_code == 200
        assert response.json() == {"days_before": [7, 1], "email": False}

    @pytest.mark.parametrize("days", [[7], [3], [1], [0]])
    def test_patch_each_allowed_value(self, days):
        user = User.objects.create_user(
            email=f"rem-{days[0]}@example.com", password=STRONG, name="Rem", email_verified=True
        )
        response = client_for(user).patch("/api/reminders/settings/", {"days_before": days}, format="json")
        assert response.status_code == 200
        assert response.json()["days_before"] == days

    def test_patch_all_four_values(self):
        user = User.objects.create_user(
            email="rem-all@example.com", password=STRONG, name="Rem", email_verified=True
        )
        client = client_for(user)
        response = client.patch("/api/reminders/settings/", {"days_before": [1, 0, 3, 7]}, format="json")
        assert response.status_code == 200
        assert response.json()["days_before"] == [7, 3, 1, 0]
        user.refresh_from_db()
        assert user.reminder_days == "7,3,1,0"

    def test_patch_empty_list_round_trip(self):
        user = User.objects.create_user(
            email="rem-empty@example.com", password=STRONG, name="Rem", email_verified=True
        )
        client = client_for(user)
        patch = client.patch("/api/reminders/settings/", {"days_before": []}, format="json")
        assert patch.status_code == 200
        assert patch.json()["days_before"] == []
        user.refresh_from_db()
        assert user.reminder_days == ""
        assert client.get("/api/reminders/settings/").json()["days_before"] == []

    def test_stored_empty_string_parses_to_empty_list(self):
        assert parse_reminder_days("") == []

    def test_format_empty_list_stores_empty_string(self):
        assert format_reminder_days([]) == ""

    @pytest.mark.parametrize("bad", [[2], [14], [-1]])
    def test_rejects_disallowed_values(self, bad):
        user = User.objects.create_user(
            email="rem-bad@example.com", password=STRONG, name="Rem", email_verified=True
        )
        response = client_for(user).patch("/api/reminders/settings/", {"days_before": bad}, format="json")
        assert response.status_code == 400
        assert_error_shape(response)
        assert "days_before" in response.json()["error"]["fields"]

    def test_rejects_duplicates(self):
        user = User.objects.create_user(
            email="rem-dup@example.com", password=STRONG, name="Rem", email_verified=True
        )
        response = client_for(user).patch(
            "/api/reminders/settings/", {"days_before": [7, 7]}, format="json"
        )
        assert response.status_code == 400
        assert "days_before" in response.json()["error"]["fields"]

    def test_rejects_non_list(self):
        user = User.objects.create_user(
            email="rem-type@example.com", password=STRONG, name="Rem", email_verified=True
        )
        response = client_for(user).patch("/api/reminders/settings/", {"days_before": 7}, format="json")
        assert response.status_code == 400
        assert_error_shape(response)
