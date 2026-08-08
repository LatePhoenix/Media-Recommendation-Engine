#!/bin/sh
# Periodically enqueue collaborative-filter edge rebuilds.
set -e
INTERVAL="${CF_REBUILD_INTERVAL_SECONDS:-86400}"
REDIS_URL="${REDIS_URL:-redis://redis:6379/0}"

echo "recommender-scheduler: interval=${INTERVAL}s redis=${REDIS_URL}"

# Warm-start shortly after boot so fresh installs get CF edges without waiting a day.
sleep 30
while true; do
  echo "recommender-scheduler: enqueue nightly_retrain_stub"
  rq enqueue --url "$REDIS_URL" workers.recommender.jobs.nightly_retrain_stub || \
    python -c "from redis import Redis; from rq import Queue; import os; q=Queue('recommender', connection=Redis.from_url(os.environ['REDIS_URL'])); q.enqueue('workers.recommender.jobs.nightly_retrain_stub'); print('enqueued')"
  sleep "$INTERVAL"
done
