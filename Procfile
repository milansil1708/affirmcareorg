web: gunicorn affirm_care.wsgi --workers $WEB_CONCURRENCY --worker-class gthread --threads 2 --timeout 20 --max-requests 1000 --max-requests-jitter 100 --access-logfile - --error-logfile -
