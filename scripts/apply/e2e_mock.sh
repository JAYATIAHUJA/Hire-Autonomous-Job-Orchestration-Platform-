#!/usr/bin/env bash
# End-to-end auto-fill against the local mock ATS (lab/mock-ats), on a running stack.
#
#   python scripts/dev.py --detach
#   bash scripts/apply/e2e_mock.sh
#
# What it does: signs in (dev-login), writes the profile basics the form needs
# (name/location/phone facts, a resume in S3, standard answers), inserts one mock
# job, swipes right (the fill run starts on its own), waits for the worker to fill
# the form in real Chromium, sends it with the typed company-name confirmation,
# then prints what the mock ATS received. Nothing touches a real employer.
set -uo pipefail
API=http://localhost:8100
MOCK=http://localhost:8180
EMAIL="e2e-$(date +%s)@example.com"
COOKIES=$(mktemp)
H=(-H "X-Requested-With: hire-web" -H "Content-Type: application/json" -b "$COOKIES" -c "$COOKIES")

say() { printf '\n== %s ==\n' "$*"; }
fail() { printf '\nFAILED: %s\n' "$*" >&2; exit 1; }
jq_field() { python3 -c "import json,sys; print(json.load(sys.stdin)$1)"; }

say "1. Sign in (dev-login)"
curl -s "${H[@]}" -X POST $API/v1/auth/dev-login -d "{\"email\":\"$EMAIL\"}" | jq_field '["id"]' >/dev/null || fail "login"
ACCOUNT_ID=$(curl -s "${H[@]}" $API/v1/me | jq_field '["id"]')
echo "account id: $ACCOUNT_ID"

say "2. Profile basics (facts the form needs)"
for f in '{"kind":"name","text":"E2E Runner"}' '{"kind":"location","text":"Bengaluru"}' '{"kind":"contact_phone","text":"+91 90000 00000"}'; do
  curl -s "${H[@]}" -X POST $API/v1/profile/facts -d "$f" | jq_field '["status"]'
done

say "3. Resume file into S3 + resume_uploads row"
UPLOAD_ID="res_e2e$(date +%s)"
printf '%%PDF-1.4 e2e resume for the mock ATS run\n' > /tmp/e2e-resume.pdf
docker cp /tmp/e2e-resume.pdf hire-api-1:/tmp/e2e-resume.pdf >/dev/null
docker exec hire-api-1 python -c "
from app.facts.storage import get_object_store
get_object_store().put('resumes/$ACCOUNT_ID/$UPLOAD_ID.pdf', open('/tmp/e2e-resume.pdf','rb').read(), 'application/pdf')
print('stored')"
docker exec hire-db-1 psql -U hire -d hire -q -c \
  "INSERT INTO resume_uploads (id, account_id, object_key, sha256, content_type, size_bytes, text_source, created_at)
   VALUES ('$UPLOAD_ID', $ACCOUNT_ID, 'resumes/$ACCOUNT_ID/$UPLOAD_ID.pdf', 'e2e', 'application/pdf', 34, 'text_layer', now());"

say "4. Standard answers (notice period + work authorisation)"
curl -s "${H[@]}" -X PUT $API/v1/me/answer-bank \
  -d '{"answers":{"notice_period":"30_days","work_authorisation_india":"yes"}}' >/dev/null
echo "saved"

say "5. Insert the mock ATS job (Acme Mock, job 4001)"
docker exec hire-db-1 psql -U hire -d hire -q -c \
  "INSERT INTO companies (name, domain, external_layoff_flag)
   SELECT 'Acme Mock', 'acme.test', false WHERE NOT EXISTS (SELECT 1 FROM companies WHERE name = 'Acme Mock');
   INSERT INTO jobs (job_id, company_id, title, location, ghost_score, risk_band, legitimacy_probability,
                     posting_age_days, repost_count, experience_level, primary_skills_json,
                     raw_description_hash, raw_description, canonical_key, is_active, source, apply_url, last_seen_at)
   SELECT 'mock-ats-4001', c.id, 'Backend Engineer (Python)', 'Bengaluru, India', 10, 'Low', 0.95,
          1, 0, 'Mid-Level (2-5 yrs)', '[]', 'mock4001', 'Build Python services.', 'mock-ats-4001',
          true, 'greenhouse', 'http://mock-ats:8000/boards/acme/jobs/4001', now()
   FROM companies c WHERE c.name = 'Acme Mock'
   ON CONFLICT (job_id) DO NOTHING;"
echo "job ready"

say "6. Swipe right (auto-start should fire)"
SWIPE=$(curl -s "${H[@]}" -X POST $API/api/applications/swipe -d '{"job_id":"mock-ats-4001","direction":"right"}')
echo "autofill_started: $(echo "$SWIPE" | jq_field '["autofill_started"]')"
APP_ID=$(echo "$SWIPE" | jq_field '["application"]["application_id"]')
[ -n "$APP_ID" ] || fail "no application id"

wait_for() {  # wait_for <statuses...> : poll the run until it leaves the working set
  for i in $(seq 1 60); do
    RUN=$(curl -s "${H[@]}" $API/api/applications/$APP_ID/autofill)
    STATUS=$(echo "$RUN" | jq_field '["status"]')
    echo "  [$i] $STATUS"
    case $STATUS in queued|filling|submit_requested|submitting) sleep 3 ;; *) break ;; esac
  done
}

wait_for
[ "$STATUS" = "ready_to_submit" ] || fail "fill ended at $STATUS: $RUN"

say "7. The live event log"
curl -s "${H[@]}" $API/api/applications/$APP_ID/autofill/events | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("run", d["run_id"], "status:", d["status"])
for e in d["events"]:
    print("  {:>2}. {}".format(e["seq"], e["label"]))'

say "8. Typed confirmation sends it"
curl -s "${H[@]}" -X POST $API/api/applications/$APP_ID/autofill/submit -d '{"company_name":"acme mock"}' >/dev/null
wait_for
[ "$STATUS" = "submitted" ] || fail "send ended at $STATUS"

say "9. What the mock ATS received"
curl -s $MOCK/_submissions | python3 -m json.tool

say "10. Pipeline card"
curl -s "${H[@]}" $API/api/applications/board | python3 -c '
import json, sys
b = json.load(sys.stdin)
print("needs_you:", b["needs_you"])
for col in b["columns"]:
    for c in col["cards"]:
        print("  {}: submission={} autofill={}".format(c["employer_name"], c["submission_status"], c["autofill"]))'

printf '\nE2E COMPLETE\n'
