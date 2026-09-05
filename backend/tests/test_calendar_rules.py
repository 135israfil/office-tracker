"""Working-day rules (D4). These decide who gets marked absent, so they get tested hard."""

import datetime as dt

import pytest
from django.core.exceptions import ValidationError

from attendance.calendar_rules import (
    is_weekend,
    is_working_day,
    local_date,
    working_days_between,
)
from attendance.models import AppSettings

# 2026-08-17 is a Monday, so the week runs Mon 17 … Sun 23.
MON = dt.date(2026, 8, 17)
TUE = dt.date(2026, 8, 18)
WED = dt.date(2026, 8, 19)
THU = dt.date(2026, 8, 20)
FRI = dt.date(2026, 8, 21)
SAT = dt.date(2026, 8, 22)
SUN = dt.date(2026, 8, 23)

FRI_SAT = [4, 5]
SAT_SUN = [5, 6]


class TestWeekendRules:
    def test_default_weekend_is_friday_saturday(self):
        assert is_weekend(FRI, FRI_SAT) is True
        assert is_weekend(SAT, FRI_SAT) is True
        assert is_weekend(SUN, FRI_SAT) is False
        assert is_weekend(MON, FRI_SAT) is False

    def test_changing_weekend_days_changes_working_days(self):
        """The Phase 2 exit criterion: this setting must actually move the boundary."""
        assert is_working_day(SUN, FRI_SAT, []) is True
        assert is_working_day(SUN, SAT_SUN, []) is False

        assert is_working_day(FRI, FRI_SAT, []) is False
        assert is_working_day(FRI, SAT_SUN, []) is True

    def test_holiday_overrides_a_working_day(self):
        assert is_working_day(WED, FRI_SAT, []) is True
        assert is_working_day(WED, FRI_SAT, [WED]) is False

    def test_no_weekend_configured_means_every_day_works(self):
        for day in (MON, FRI, SAT, SUN):
            assert is_working_day(day, [], []) is True


class TestWorkingDaysBetween:
    def test_counts_a_full_week_with_friday_saturday_weekend(self):
        days = working_days_between(MON, SUN, FRI_SAT, [])
        assert days == [MON, TUE, WED, THU, SUN]

    def test_counts_a_full_week_with_saturday_sunday_weekend(self):
        days = working_days_between(MON, SUN, SAT_SUN, [])
        assert days == [MON, TUE, WED, THU, FRI]

    def test_holidays_are_excluded(self):
        days = working_days_between(MON, THU, FRI_SAT, [TUE, WED])
        assert days == [MON, THU]

    def test_reversed_range_is_empty_not_an_error(self):
        assert working_days_between(SUN, MON, FRI_SAT, []) == []

    def test_single_day_range(self):
        assert working_days_between(MON, MON, FRI_SAT, []) == [MON]
        assert working_days_between(FRI, FRI, FRI_SAT, []) == []


@pytest.mark.django_db
class TestLocalDate:
    def test_utc_instant_maps_to_office_local_date(self):
        settings_obj = AppSettings.load()
        settings_obj.timezone = "Asia/Dhaka"  # UTC+6
        settings_obj.save()

        # 23:30 UTC on the 18th is 05:30 on the 19th in Dhaka. Getting this wrong
        # would file a check-in against the previous day.
        instant = dt.datetime(2026, 8, 18, 23, 30, tzinfo=dt.timezone.utc)
        assert local_date(instant, settings_obj) == dt.date(2026, 8, 19)

        # 03:00 UTC is 09:00 the same day in Dhaka.
        instant = dt.datetime(2026, 8, 19, 3, 0, tzinfo=dt.timezone.utc)
        assert local_date(instant, settings_obj) == dt.date(2026, 8, 19)

    def test_naive_datetime_is_rejected(self):
        settings_obj = AppSettings.load()
        with pytest.raises(ValueError, match="aware"):
            local_date(dt.datetime(2026, 8, 19, 3, 0), settings_obj)


@pytest.mark.django_db
class TestAppSettingsValidation:
    def test_is_a_singleton(self):
        first = AppSettings.load()
        second = AppSettings.load()
        assert first.pk == second.pk == AppSettings.SINGLETON_PK

        # Creating "another" settings row folds into the singleton rather than
        # raising or producing a second row that half the code would never read.
        AppSettings.objects.create(office_name="Second row attempt")
        assert AppSettings.objects.count() == 1
        assert AppSettings.load().office_name == "Second row attempt"

    def test_cannot_be_deleted(self):
        with pytest.raises(ValidationError):
            AppSettings.load().delete()

    def test_rejects_making_every_day_a_weekend(self):
        settings_obj = AppSettings.load()
        settings_obj.weekend_days = [0, 1, 2, 3, 4, 5, 6]
        with pytest.raises(ValidationError) as exc:
            settings_obj.full_clean()
        assert "weekend_days" in exc.value.message_dict

    def test_rejects_unknown_timezone(self):
        settings_obj = AppSettings.load()
        settings_obj.timezone = "Mars/Olympus_Mons"
        with pytest.raises(ValidationError) as exc:
            settings_obj.full_clean()
        assert "timezone" in exc.value.message_dict

    def test_rejects_end_before_start(self):
        settings_obj = AppSettings.load()
        settings_obj.default_start_time = dt.time(18, 0)
        settings_obj.default_end_time = dt.time(9, 0)
        with pytest.raises(ValidationError) as exc:
            settings_obj.full_clean()
        assert "default_end_time" in exc.value.message_dict

    def test_rejects_zero_retention(self):
        settings_obj = AppSettings.load()
        settings_obj.activity_retention_days = 0
        with pytest.raises(ValidationError) as exc:
            settings_obj.full_clean()
        assert "activity_retention_days" in exc.value.message_dict
