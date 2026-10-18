variable "aws_region" {
  description = "Region AWS, w którym wdrażana jest infrastruktura"
  type        = string
  default     = "eu-central-1"
}

variable "project_name" {
  description = "Nazwa projektu używana do tagowania i prefiksowania zasobów"
  type        = string
  default     = "aether-tower"
}

variable "environment" {
  description = "Nazwa środowiska (np. dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "cluster_name" {
  description = "Nazwa klastra Amazon EKS"
  type        = string
  default     = "aether-tower-eks"
}

variable "vpc_cidr" {
  description = "Główny zakres adresów IP sieci VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Lista stref dostępności (AZ) dla VPC i EKS"
  type        = list(string)
  default     = ["eu-central-1a", "eu-central-1b"]
}

variable "node_instance_types" {
  description = "Typ instancji EC2 dla węzłów roboczych EKS"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_capacity_type" {
  description = "Typ rozliczania instancji: SPOT (tanie, optymalne do testów) lub ON_DEMAND"
  type        = string
  default     = "SPOT"
}
