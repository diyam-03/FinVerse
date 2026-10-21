# Deploying FinVerse

Two parts: get it live on AWS (section 1), then put it on GitHub (section 2). Section 3 is optional.

## 1. Deploy to AWS (about 15 minutes, easiest route: CloudShell)

CloudShell is a terminal inside the AWS console. It already has the AWS CLI and SAM CLI, and it is
already logged in as you, so there are no access keys to create.

1. Sign in to the AWS console and switch the region to **Asia Pacific (Mumbai) ap-south-1**
   (top-right region menu). The deploy script defaults to this region.
2. Click the **CloudShell** icon (`>_`) in the top bar and wait for the prompt.
3. **Actions > Upload file** and upload `finverse-3d.zip`, then run:
   ```bash
   unzip finverse-3d.zip
   cd finverse
   bash deploy.sh
   ```
4. The first run takes 5-10 minutes (CloudFront is slow to create). It finishes with:
   ```
   Website : https://dxxxxxxxxxxxx.cloudfront.net
   API     : https://xxxxxxxx.execute-api.ap-south-1.amazonaws.com/health
   ```
5. Open the Website URL, press **Load demo**, **Save**, then **Run simulation**.
   Open the API URL: it should return `{"status":"ok","storage":"dynamodb"}`.

Re-deploying after a change is the same `bash deploy.sh`.

### If something goes wrong
- **"Stack is in ROLLBACK_COMPLETE"**: `aws cloudformation delete-stack --stack-name finverse`, wait, rerun.
- **CloudFront not allowed on a brand-new account**: AWS sometimes asks new accounts to verify before creating
  CloudFront distributions. Open a support case or add a card/verify the account, then rerun.
- **Page loads but simulation fails**: open CloudWatch > Log groups and read the worker log group
  (7-day retention). The `WorkerErrorAlarm` and `DlqAlarm` in the template fire on failures.

### Cost
Pay-per-request DynamoDB, small Lambdas, API throttling and no always-on resources, so a student demo
costs close to nothing. To remove everything:
```bash
BUCKET=$(aws cloudformation describe-stacks --stack-name finverse --query "Stacks[0].Outputs[?OutputKey=='SiteBucket'].OutputValue" --output text)
aws s3 rm "s3://$BUCKET" --recursive
aws cloudformation delete-stack --stack-name finverse
```

## 2. Put it on GitHub

1. On github.com click **New repository**. Name it `finverse`. Leave "Add README / .gitignore / license"
   **unticked** (the project already has them). Create it.
2. On your computer, unzip the project, open a terminal in the `finverse` folder and run
   (replace `YOUR-USERNAME`):
   ```bash
   git init -b main
   git add .
   git commit -m "FinVerse: financial digital twin and scenario simulator"
   git remote add origin https://github.com/YOUR-USERNAME/finverse.git
   git push -u origin main
   ```
3. Open the **Actions** tab. The **CI** workflow runs your tests and validates the SAM template on every push.

Nothing secret is in the repo: `frontend/config.js` only holds an empty local default, and `deploy.sh`
writes the real API URL to S3 at deploy time. `.gitignore` already excludes `.aws-sam/` and `samconfig.toml`.

## 3. Optional: deploy from GitHub with one click

Skip this if section 1 works for you. It lets the **Deploy to AWS** workflow run `deploy.sh` from the Actions tab.

1. AWS console > IAM > Identity providers > **Add provider** > OpenID Connect:
   provider URL `https://token.actions.githubusercontent.com`, audience `sts.amazonaws.com`.
2. IAM > Roles > **Create role** > Web identity > that provider, audience `sts.amazonaws.com`, and restrict the
   trust to your repo (`repo:YOUR-USERNAME/finverse:*`).
3. Attach permissions. For a student project `AdministratorAccess` works but is broad; remove the role when you are done.
4. In the GitHub repo: Settings > Secrets and variables > Actions > New secret named `AWS_ROLE_ARN` with the role's ARN.
5. Actions tab > **Deploy to AWS** > Run workflow.
