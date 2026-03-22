# Deploying to GCP Cloud Run + Cloud Scheduler

This guide walks through deploying the Telegram message fetcher as a Cloud Run Job
triggered daily by Cloud Scheduler.

## Prerequisites

- [Google Cloud SDK (`gcloud`)](https://cloud.google.com/sdk/docs/install) installed and authenticated
- GCP project with billing enabled (project ID: `telegram-bot-490722`)
- Docker installed locally (or use Cloud Build — see step 4)

Set your project:

```bash
export PROJECT_ID=telegram-bot-490722
export REGION=me-west1
gcloud config set project $PROJECT_ID
```

## 1. Generate the Telethon StringSession

Run this once locally (requires interactive phone/code verification):

```bash
poetry run python generate_session.py
```

Copy the output string — you'll store it as a secret in the next step.

## 2. Store secrets in Secret Manager

Enable the API first:

```bash
gcloud services enable secretmanager.googleapis.com
```

Create each secret:

```bash
echo -n "1857876" | gcloud secrets create telegram-api-id --data-file=-
echo -n "13d15d14c7c4117c9603b0c7b1298f42" | gcloud secrets create telegram-api-hash --data-file=-
echo -n "+972543382381" | gcloud secrets create telegram-phone --data-file=-
echo -n "PASTE_YOUR_STRING_SESSION_HERE" | gcloud secrets create telegram-string-session --data-file=-
echo -n "your.email@gmail.com" | gcloud secrets create gmail-address --data-file=-
echo -n "YOUR_APP_PASSWORD" | gcloud secrets create gmail-app-password --data-file=-
```

To generate a Gmail app password:
1. Go to https://myaccount.google.com/apppasswords (requires 2FA enabled)
2. Create a new app password (name it "telegram-bot" or similar)
3. Copy the 16-character password and use it above

Grant the default Compute Engine service account access to the secrets:

```bash
export SA=$(gcloud iam service-accounts list \
  --filter="displayName:Compute Engine default" \
  --format="value(email)")

for SECRET in telegram-api-id telegram-api-hash telegram-phone telegram-string-session gmail-address gmail-app-password; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:$SA" \
    --role="roles/secretmanager.secretAccessor"
done
```

Grant the service account permission to sign URLs via the IAM signBlob API
(used instead of a key file for `generate_signed_url`):

```bash
gcloud iam service-accounts add-iam-policy-binding $SA \
  --member="serviceAccount:$SA" \
  --role="roles/iam.serviceAccountTokenCreator"
```

## 3. Create the reports GCS bucket

```bash
export REPORTS_BUCKET=my-telegram-bot-reports

gcloud storage buckets create gs://$REPORTS_BUCKET --location=$REGION

gcloud storage buckets add-iam-policy-binding gs://$REPORTS_BUCKET \
  --member="allUsers" \
  --role="roles/storage.objectViewer"
```

Reports will be publicly accessible at:
`https://storage.googleapis.com/$REPORTS_BUCKET/telegram/YYYYMMDD_HHMMSS/report.html`

## 4. Build and push the Docker image

Enable Artifact Registry and create a repository:

```bash
gcloud services enable artifactregistry.googleapis.com

gcloud artifacts repositories create telegram-bot \
  --repository-format=docker \
  --location=$REGION
```

Build and push (using Cloud Build so you don't need Docker locally):

```bash
export IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/telegram-bot/fetch-messages:latest

gcloud builds submit --tag $IMAGE .
```

Or build locally and push:

```bash
docker build -t $IMAGE .
docker push $IMAGE
```

## 5. Create the Cloud Run Job

```bash
gcloud services enable run.googleapis.com

gcloud run jobs create telegram-fetch-messages \
  --image=$IMAGE \
  --region=$REGION \
  --memory=1Gi \
  --task-timeout=30m \
  --set-secrets="TELEGRAM_API_ID=telegram-api-id:latest,TELEGRAM_API_HASH=telegram-api-hash:latest,TELEGRAM_PHONE=telegram-phone:latest,TELEGRAM_STRING_SESSION=telegram-string-session:latest,GMAIL_ADDRESS=gmail-address:latest,GMAIL_APP_PASSWORD=gmail-app-password:latest" \
  --set-env-vars="GCS_BUCKET=my-telegram-bot-media-bucker,GCS_REPORTS_BUCKET=$REPORTS_BUCKET,GCS_SIGNED_URL_EXPIRY_DAYS=7"
```

Test it manually:

```bash
gcloud run jobs execute telegram-fetch-messages --region=$REGION --wait
```

## 6. Create the Cloud Scheduler trigger

Enable the API:

```bash
gcloud services enable cloudscheduler.googleapis.com
```

Create a service account for the scheduler to invoke the job:

```bash
gcloud iam service-accounts create scheduler-invoker \
  --display-name="Cloud Scheduler Job Invoker"

gcloud run jobs add-iam-policy-binding telegram-fetch-messages \
  --region=$REGION \
  --member="serviceAccount:scheduler-invoker@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

Create the scheduled trigger (daily at 8:00 AM Israel time):

```bash
gcloud scheduler jobs create http telegram-daily-fetch \
  --location=$REGION \
  --schedule="0 8 * * *" \
  --time-zone="Asia/Jerusalem" \
  --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/telegram-fetch-messages:run" \
  --http-method=POST \
  --oauth-service-account-email="scheduler-invoker@$PROJECT_ID.iam.gserviceaccount.com"
```

## 7. Set up CI/CD (automated deploy on git push)

See `.github/workflows/deploy.yml`. After the one-time setup below, every push
to `main` will automatically rebuild and deploy — no manual commands needed.

### One-time setup

1. Create a GCP service account for GitHub Actions:

```bash
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions deployer"

export GH_SA=github-actions@${PROJECT_ID}.iam.gserviceaccount.com

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$GH_SA" \
  --role="roles/cloudbuild.builds.builder"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$GH_SA" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$GH_SA" \
  --role="roles/artifactregistry.writer"

gcloud iam service-accounts add-iam-policy-binding \
  $(gcloud iam service-accounts list --filter="displayName:Compute Engine default" --format="value(email)") \
  --member="serviceAccount:$GH_SA" \
  --role="roles/iam.serviceAccountUser"
```

2. Set up Workload Identity Federation (keyless auth — no JSON keys):

```bash
gcloud iam workload-identity-pools create github-pool \
  --location="global" \
  --display-name="GitHub Actions pool"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

gcloud iam service-accounts add-iam-policy-binding $GH_SA \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')/locations/global/workloadIdentityPools/github-pool/attribute.repository/hthrrr/telegram-bot"
```

3. Add these as GitHub repository secrets (Settings > Secrets and variables > Actions):

   - `GCP_PROJECT_ID` = `telegram-bot-490722`
   - `GCP_WIF_PROVIDER` = the full provider name (output of the command above, looks like `projects/123456/locations/global/workloadIdentityPools/github-pool/providers/github-provider`)
   - `GCP_SA_EMAIL` = `github-actions@telegram-bot-490722.iam.gserviceaccount.com`

## Updating the image (manual fallback)

```bash
gcloud builds submit --tag $IMAGE .
gcloud run jobs update telegram-fetch-messages --image=$IMAGE --region=$REGION
```
