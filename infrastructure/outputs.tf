# ---------------------------------------------------------------------------
# Wyjścia (Outputs) – przydatne parametry po wdrożeniu infrastruktury
# ---------------------------------------------------------------------------

output "cluster_name" {
  description = "Nazwa utworzonego klastra EKS"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "Adres URL API klastra Kubernetes"
  value       = aws_eks_cluster.main.endpoint
}

output "configure_kubectl" {
  description = "Komenda do pobrania konfiguracji klastra (kubeconfig) na lokalną maszynę"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${aws_eks_cluster.main.name}"
}

output "ecr_repository_urls" {
  description = "Adresy URL rejestrów Amazon ECR do wypchnięcia obrazów Docker"
  value = {
    for k, v in aws_ecr_repository.services : k => v.repository_url
  }
}

output "vpc_id" {
  description = "Identyfikator utworzonej sieci VPC"
  value       = aws_vpc.main.id
}

output "codebuild_project_name" {
  description = "Nazwa projektu CodeBuild (runner pipeline'u)"
  value       = aws_codebuild_project.deploy.name
}

output "pipeline_name" {
  description = "Nazwa potoku AWS CodePipeline"
  value       = aws_codepipeline.main.name
}

output "authorize_github_connection" {
  description = "KROK RĘCZNY po terraform apply: zatwierdź połączenie z GitHub (status PENDING -> AVAILABLE)"
  value       = "https://${var.aws_region}.console.aws.amazon.com/codesuite/settings/connections?region=${var.aws_region} (połączenie: ${aws_codestarconnections_connection.github.name})"
}

output "start_pipeline" {
  description = "Komenda ręcznie uruchamiająca pipeline (np. po zatwierdzeniu połączenia z GitHub)"
  value       = "aws codepipeline start-pipeline-execution --region ${var.aws_region} --name ${aws_codepipeline.main.name}"
}

output "get_frontend_url" {
  description = "Komenda pokazująca publiczny adres aplikacji (po wdrożeniu)"
  value       = "kubectl -n aether-tower get svc frontend -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'"
}
