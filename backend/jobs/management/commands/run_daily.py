from datetime import date

from django.core.management.base import BaseCommand, CommandError

from core.dates import today_dhaka
from jobs import services as job_services


class Command(BaseCommand):
    help = "Run daily billing maintenance (charges, expirations, trial activation)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            dest="run_date",
            help="Run as of this calendar date (YYYY-MM-DD). Defaults to today in Dhaka.",
        )

    def handle(self, *args, **options):
        raw = options.get("run_date")
        if raw:
            try:
                run_date = date.fromisoformat(raw)
            except ValueError as exc:
                raise CommandError("Invalid --date; use YYYY-MM-DD.") from exc
        else:
            run_date = today_dhaka()

        result = job_services.run_daily(run_date)
        if result is None:
            return
        self.stdout.write(
            "expired={expired} trials_activated={trials_activated} "
            "plans_processed={plans_processed} charges_created={charges_created} "
            "charge_errors={charge_errors} charges_locked={charges_locked}".format(**result)
        )
