# ---------------------------------------------------------------------------
# Rejestry Amazon ECR dla mikrousług Aether Tower OS
# ---------------------------------------------------------------------------

locals {
  services = [
    "frontend",
    "reservation-service",
    "user-notification-service"
  ]
}

resource "aws_ecr_repository" "services" {
  for_each             = toset(local.services)
  name                 = "${var.project_name}/${each.key}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # Pozwala na automatyczne usunięcie repozytorium przy terraform destroy nawet z obrazami

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Service = each.key
  }
}
