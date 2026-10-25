# ---------------------------------------------------------------------------
# AWS CodePipeline – orkiestracja przepływu pracy CI/CD
#
#   [Source: GitHub przez CodeConnections] --> [Build: CodeBuild (buildspec.yml)]
#
# Pipeline sam wykrywa push na gałąź var.github_branch i uruchamia CodeBuild.
# Nie wymaga tokena GitHub – autoryzacja odbywa się raz, w konsoli AWS, przez
# aplikację "AWS Connector for GitHub" (patrz output `authorize_github_connection`).
# ---------------------------------------------------------------------------

# --- Połączenie z GitHub (CodeConnections) -----------------------------------
# UWAGA: po `terraform apply` połączenie ma status PENDING. Trzeba je raz zatwierdzić
# ręcznie w konsoli (Developer Tools -> Settings -> Connections -> "Update pending connection").
# Do tego czasu etap Source pipeline'u kończy się błędem.
resource "aws_codestarconnections_connection" "github" {
  name          = "${var.project_name}-github"
  provider_type = "GitHub"
}

# --- Bucket na artefakty (kod źródłowy przekazywany między etapami) ----------
resource "aws_s3_bucket" "pipeline_artifacts" {
  bucket        = "${var.project_name}-pipeline-artifacts-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # pozwala na terraform destroy mimo zawartości bucketu
}

resource "aws_s3_bucket_public_access_block" "pipeline_artifacts" {
  bucket                  = aws_s3_bucket.pipeline_artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "pipeline_artifacts" {
  bucket = aws_s3_bucket.pipeline_artifacts.id

  rule {
    id     = "expire-old-artifacts"
    status = "Enabled"

    filter {}

    expiration {
      days = 14
    }
  }
}

# --- Rola IAM dla CodePipeline ----------------------------------------------
resource "aws_iam_role" "codepipeline" {
  name = "${var.project_name}-codepipeline-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "codepipeline.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "codepipeline" {
  name = "${var.project_name}-codepipeline-policy"
  role = aws_iam_role.codepipeline.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Artifacts"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.pipeline_artifacts.arn}/*"
      },
      {
        Sid      = "ArtifactsBucket"
        Effect   = "Allow"
        Action   = ["s3:GetBucketLocation", "s3:GetBucketVersioning", "s3:ListBucket"]
        Resource = aws_s3_bucket.pipeline_artifacts.arn
      },
      {
        Sid      = "UseGithubConnection"
        Effect   = "Allow"
        Action   = "codestar-connections:UseConnection"
        Resource = aws_codestarconnections_connection.github.arn
      },
      {
        Sid    = "RunCodeBuild"
        Effect = "Allow"
        Action = [
          "codebuild:StartBuild",
          "codebuild:BatchGetBuilds"
        ]
        Resource = aws_codebuild_project.deploy.arn
      }
    ]
  })
}

# --- Pipeline ----------------------------------------------------------------
resource "aws_codepipeline" "main" {
  name           = "${var.project_name}-pipeline"
  role_arn       = aws_iam_role.codepipeline.arn
  pipeline_type  = "V2"
  execution_mode = "QUEUED" # kolejne pushe czekają w kolejce zamiast nadpisywać trwający deploy

  artifact_store {
    type     = "S3"
    location = aws_s3_bucket.pipeline_artifacts.bucket
  }

  stage {
    name = "Source"

    action {
      name             = "GitHub"
      category         = "Source"
      owner            = "AWS"
      provider         = "CodeStarSourceConnection"
      version          = "1"
      output_artifacts = ["source_output"]
      namespace        = "SourceVariables" # udostępnia m.in. #{SourceVariables.CommitId}

      configuration = {
        ConnectionArn        = aws_codestarconnections_connection.github.arn
        FullRepositoryId     = var.github_repository_id
        BranchName           = var.github_branch
        OutputArtifactFormat = "CODE_ZIP"
        DetectChanges        = "true" # automatyczne uruchomienie po git push
      }
    }
  }

  stage {
    name = "Build"

    action {
      name            = "BuildAndDeploy"
      category        = "Build"
      owner           = "AWS"
      provider        = "CodeBuild"
      version         = "1"
      input_artifacts = ["source_output"]

      configuration = {
        ProjectName = aws_codebuild_project.deploy.name
        # Przekazanie skrótu commita do buildspec.yml (tag obrazów Docker).
        EnvironmentVariables = jsonencode([
          {
            name  = "COMMIT_ID"
            value = "#{SourceVariables.CommitId}"
            type  = "PLAINTEXT"
          }
        ])
      }
    }
  }

  depends_on = [aws_iam_role_policy.codepipeline]
}
