# ---------------------------------------------------------------------------
# AWS CodeBuild – serwerowe środowisko wykonawcze (runner) dla pipeline'u.
#
# CodeBuild NIE pobiera kodu z GitHuba samodzielnie ani nie ma własnego webhooka –
# kod dostaje od AWS CodePipeline (pipeline.tf) jako artefakt źródłowy.
# Instrukcje wykonuje wg buildspec.yml z katalogu głównego repozytorium:
#   login do ECR -> docker build -> docker push -> kubectl apply (rolling update).
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

locals {
  ecr_registry   = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
  codebuild_name = "${var.project_name}-deploy"
}

# --- Logi ------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "codebuild" {
  name              = "/aws/codebuild/${local.codebuild_name}"
  retention_in_days = 14 # logi budowania to materiał dowodowy do pracy, ale nie muszą kosztować w nieskończoność
}

# --- Rola IAM dla CodeBuild --------------------------------------------------
resource "aws_iam_role" "codebuild" {
  name = "${var.project_name}-codebuild-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "codebuild.amazonaws.com"
      }
    }]
  })
}

# Zasada najmniejszych uprawnień: logi, odczyt artefaktu źródłowego z bucketu pipeline'u,
# wypychanie obrazów TYLKO do trzech naszych repozytoriów ECR oraz odczyt opisu klastra
# (potrzebny do `aws eks update-kubeconfig`).
# Uprawnienia WEWNĄTRZ klastra Kubernetes nadaje osobno aws_eks_access_entry poniżej.
resource "aws_iam_role_policy" "codebuild" {
  name = "${var.project_name}-codebuild-policy"
  role = aws_iam_role.codebuild.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.codebuild.arn}:*"
      },
      {
        Sid    = "PipelineArtifacts"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.pipeline_artifacts.arn}/*"
      },
      {
        Sid      = "PipelineBucket"
        Effect   = "Allow"
        Action   = ["s3:GetBucketLocation", "s3:GetBucketVersioning"]
        Resource = aws_s3_bucket.pipeline_artifacts.arn
      },
      {
        Sid      = "EcrLogin"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "EcrPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage"
        ]
        Resource = [for repo in aws_ecr_repository.services : repo.arn]
      },
      {
        Sid      = "EksDescribe"
        Effect   = "Allow"
        Action   = "eks:DescribeCluster"
        Resource = aws_eks_cluster.main.arn
      }
    ]
  })
}

# --- Dostęp CodeBuild do API Kubernetes -------------------------------------
resource "aws_eks_access_entry" "codebuild" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = aws_iam_role.codebuild.arn
  type          = "STANDARD"
}

# AmazonEKSClusterAdminPolicy jest potrzebna, bo deploy tworzy zasoby poziomu klastra
# (Namespace, StorageClass). Dla środowiska produkcyjnego warto zawęzić uprawnienia.
resource "aws_eks_access_policy_association" "codebuild" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = aws_iam_role.codebuild.arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"

  access_scope {
    type = "cluster"
  }

  depends_on = [aws_eks_access_entry.codebuild]
}

# --- Projekt CodeBuild -------------------------------------------------------
resource "aws_codebuild_project" "deploy" {
  name          = local.codebuild_name
  description   = "Runner pipeline'u: buduje obrazy Aether Tower OS, wypycha do ECR i wdraża na EKS (rolling update)"
  service_role  = aws_iam_role.codebuild.arn
  build_timeout = 30

  # Źródło i artefakty zarządzane przez CodePipeline.
  source {
    type      = "CODEPIPELINE"
    buildspec = "buildspec.yml"
  }

  artifacts {
    type = "CODEPIPELINE"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/standard:7.0"
    type                        = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode             = true # wymagane do uruchomienia demona Dockera (docker build)

    environment_variable {
      name  = "AWS_REGION"
      value = var.aws_region
    }
    environment_variable {
      name  = "CLUSTER_NAME"
      value = aws_eks_cluster.main.name
    }
    environment_variable {
      name  = "ECR_REGISTRY"
      value = local.ecr_registry
    }
    environment_variable {
      name  = "PROJECT_NAME"
      value = var.project_name
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name = aws_cloudwatch_log_group.codebuild.name
    }
  }

  depends_on = [
    aws_iam_role_policy.codebuild,
    aws_eks_access_policy_association.codebuild,
  ]
}
