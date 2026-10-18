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
