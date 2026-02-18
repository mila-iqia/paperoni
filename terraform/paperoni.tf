
#############
# Variables #
#############

variable "project_id" {
  type        = string
  description = "Project ID"
}

variable "gh_service_owner" {
  type        = string
  description = "Owner of the repository to deploy from"
}

variable "gh_service_repo" {
  type        = string
  description = "Repository to deploy from"
}

variable "gh_service_branch" {
  type        = string
  description = "Repository branch to deploy from"
}

variable "gh_config_owner" {
  type        = string
  description = "Owner of the repository to configure from"
}

variable "gh_config_repo" {
  type        = string
  description = "Repository to configure from"
}

variable "gh_config_branch" {
  type        = string
  description = "Repository branch to configure from"
}

variable "google_region" {
  type        = string
  description = "Google deployment region"
}

variable "timezone" {
  type        = string
  description = "Timezone for scheduling"
}

variable "serieux_password" {
  type        = string
  description = "Serieux password"
  sensitive   = true
}

#################
# Main settings #
#################

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.19.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

provider "google" {
  project = var.project_id
}

data "google_project" "paperoni" {
  project_id = var.project_id
}

###############
# Permissions #
###############

resource "google_service_account" "paperoni_build" {
  account_id   = "paperoni-build"
  display_name = "Paperoni build account"
}

resource "google_service_account" "paperoni_user" {
  account_id   = "paperoni-user"
  display_name = "Paperoni API service account"
}

resource "google_project_iam_binding" "firestore" {
  project = data.google_project.paperoni.project_id
  role    = "roles/datastore.user"
  members = [google_service_account.paperoni_user.member]
}

resource "google_project_iam_binding" "cloud_run_developer" {
  project = data.google_project.paperoni.project_id
  role    = "roles/run.developer"
  members = [
    google_service_account.paperoni_build.member
  ]
}

resource "google_project_iam_binding" "cloud_run_admin" {
  project = data.google_project.paperoni.project_id
  role    = "roles/run.admin"
  members = [
    "serviceAccount:${data.google_project.paperoni.number}-compute@developer.gserviceaccount.com"
  ]
}

resource "google_project_iam_binding" "cloud_build_sa" {
  project = data.google_project.paperoni.project_id
  role    = "roles/cloudbuild.serviceAgent"
  members = [
    "serviceAccount:service-${data.google_project.paperoni.number}@gcp-sa-cloudbuild.iam.gserviceaccount.com",
    google_service_account.paperoni_build.member
  ]
}

resource "google_project_iam_binding" "secretmanager_accessor" {
  project = data.google_project.paperoni.project_id
  role    = "roles/secretmanager.secretAccessor"
  members = [
    "serviceAccount:service-${data.google_project.paperoni.number}@gcp-sa-cloudbuild.iam.gserviceaccount.com",
    google_service_account.paperoni_build.member,
    google_service_account.paperoni_user.member
  ]
}

resource "google_service_account_iam_binding" "paperoni_user_sa_iam" {
  service_account_id = google_service_account.paperoni_user.name
  role               = "roles/iam.serviceAccountUser"
  members            = [google_service_account.paperoni_build.member]
}

# Required for Cloud Build to deploy Cloud Run services
resource "google_service_account_iam_member" "paperoni_build_act_as_compute" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/${data.google_project.paperoni.number}-compute@developer.gserviceaccount.com"
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.paperoni_build.member
}

resource "google_storage_bucket_iam_member" "paperoni_user_cache" {
  bucket = google_storage_bucket.paperoni_cache.name
  role   = "roles/storage.objectUser"
  member = google_service_account.paperoni_user.member
}

resource "google_storage_bucket_iam_member" "paperoni_user_config" {
  bucket = google_storage_bucket.paperoni_config.name
  role   = "roles/storage.objectUser"
  member = google_service_account.paperoni_user.member
}

resource "google_cloud_run_v2_service_iam_member" "paperoni_web_invoker" {
  name     = google_cloud_run_v2_service.paperoni_web.name
  location = google_cloud_run_v2_service.paperoni_web.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_job_iam_member" "paperoni_scrape_invoker" {
  name     = google_cloud_run_v2_job.paperoni_scrape.name
  location = google_cloud_run_v2_job.paperoni_scrape.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_project.paperoni.number}-compute@developer.gserviceaccount.com"
}

###################
# Enable services #
###################

resource "google_project_service" "artifact_registry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloud_run" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloud_build" {
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "firestore" {
  service            = "firestore.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloud_storage" {
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloud_scheduler" {
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

###########
# Secrets #
###########

resource "google_secret_manager_secret" "serieux_password" {
  secret_id = "serieux_password"

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "serieux_password" {
  secret      = google_secret_manager_secret.serieux_password.id
  secret_data = var.serieux_password
}

##################
# Storage buckets #
##################

resource "google_storage_bucket" "paperoni_config" {
  name                        = "paperoni-config"
  location                    = var.google_region
  uniform_bucket_level_access = true
  depends_on                  = [google_project_service.cloud_storage]
}

resource "google_storage_bucket" "paperoni_cache" {
  name                        = "paperoni-cache"
  location                    = var.google_region
  uniform_bucket_level_access = true
  depends_on                  = [google_project_service.cloud_storage]
}

resource "google_firestore_database" "paperoni_db" {
  name                                = "paperoni-db"
  location_id                         = var.google_region
  type                                = "FIRESTORE_NATIVE"
  database_edition                    = "ENTERPRISE"
  mongodb_compatible_data_access_mode = "DATA_ACCESS_MODE_ENABLED"
  delete_protection_state             = "DELETE_PROTECTION_DISABLED"
  deletion_policy                     = "DELETE"
}

#########
# Build #
#########

resource "google_artifact_registry_repository" "paperoni_img" {
  location      = var.google_region
  repository_id = "paperoni-img"
  description   = "Repository for built paperoni image for cloud run deployment"
  format        = "DOCKER"

  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "delete-untagged"
    action = "DELETE"
    condition {
      tag_state = "UNTAGGED"
    }
  }
  cleanup_policies {
    id     = "keep-new-untagged"
    action = "KEEP"
    condition {
      tag_state  = "UNTAGGED"
      newer_than = "7d"
    }
  }
  cleanup_policies {
    id     = "keep-minimum-versions"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }
}

resource "google_cloudbuild_trigger" "paperoni_build_trigger" {
  name            = "paperoni-trigger"
  description     = "Builds the Paperoni container"
  location        = var.google_region
  service_account = google_service_account.paperoni_build.name

  github {
    owner = var.gh_service_owner
    name  = var.gh_service_repo
    push {
      branch = var.gh_service_branch
    }
  }

  build {
    step {
      name       = "ghcr.io/astral-sh/uv:python3.14-trixie-slim"
      entrypoint = "sh"
      args = [
        "-c",
        "uv export --format requirements.txt --no-dev --no-annotate --no-hashes --group cloud --output-file requirements.txt"
      ]
    }
    step {
      name       = "gcr.io/k8s-skaffold/pack"
      entrypoint = "pack"
      args = [
        "build",
        "--builder=gcr.io/buildpacks/builder:google-24",
        "--publish", "${google_artifact_registry_repository.paperoni_img.registry_uri}/paperoni:$COMMIT_SHA",
      ]
    }
    step {
      name       = "gcr.io/cloud-builders/gcloud"
      entrypoint = "gcloud"
      args = [
        "run",
        "services",
        "update",
        "paperoni-web",
        "--region", "${var.google_region}",
        "--image", "${google_artifact_registry_repository.paperoni_img.registry_uri}/paperoni:$COMMIT_SHA",
      ]
    }
    step {
      name       = "gcr.io/cloud-builders/gcloud"
      entrypoint = "gcloud"
      args = [
        "run",
        "jobs",
        "update",
        "paperoni-scrape",
        "--region", "${var.google_region}",
        "--image", "${google_artifact_registry_repository.paperoni_img.registry_uri}/paperoni:$COMMIT_SHA",
      ]
    }
    options {
      logging = "CLOUD_LOGGING_ONLY"
    }
  }
}

resource "google_cloudbuild_trigger" "paperoni_config_trigger" {
  name            = "paperoni-config-trigger"
  description     = "Syncs paperoni-config/cloud to GCS on push"
  location        = var.google_region
  service_account = google_service_account.paperoni_build.name

  github {
    owner = var.gh_config_owner
    name  = var.gh_config_repo
    push {
      branch = var.gh_config_branch
    }
  }

  build {
    step {
      name = "gcr.io/google.com/cloudsdktool/cloud-sdk"
      args = [
        "gcloud",
        "storage",
        "rsync",
        ".",
        "gs://${google_storage_bucket.paperoni_config.name}",
        "--recursive",
        "--delete-unmatched-destination-objects",
      ]
    }
    step {
      name       = "gcr.io/cloud-builders/gcloud"
      entrypoint = "gcloud"
      args = [
        "run",
        "services",
        "update",
        "paperoni-web",
        "--region", "${var.google_region}",
        "--update-env-vars", "CONFIG_REVISION=$$BUILD_ID",
      ]
    }
    options {
      logging = "CLOUD_LOGGING_ONLY"
    }
  }
}

###########
# Service #
###########

locals {
  mongo_uri = "mongodb://${google_firestore_database.paperoni_db.uid}.${google_firestore_database.paperoni_db.location_id}.firestore.goog:443/${google_firestore_database.paperoni_db.name}?loadBalanced=true&tls=true&retryWrites=false&authMechanism=MONGODB-OIDC&authMechanismProperties=ENVIRONMENT:gcp,TOKEN_RESOURCE:FIRESTORE"
}

resource "google_cloud_run_v2_service" "paperoni_web" {
  name     = "paperoni-web"
  location = var.google_region

  scaling {
    max_instance_count = 1
  }

  template {
    service_account = google_service_account.paperoni_user.email

    containers {
      image = "gcr.io/cloudrun/hello"

      env {
        name  = "GIFNOC_FILE"
        value = "/paperoni-config/paperoni.yaml"
      }

      env {
        name = "SERIEUX_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.serieux_password.id
            version = "latest"
          }
        }
      }

      env {
        name  = "MONGODB_NAME"
        value = google_firestore_database.paperoni_db.name
      }

      env {
        name  = "MONGODB_CONNECTION"
        value = local.mongo_uri
      }

      volume_mounts {
        name       = "gcs_cache"
        mount_path = "/paperoni-cache"
      }

      volume_mounts {
        name       = "gcs_config"
        mount_path = "/paperoni-config"
      }
    }

    volumes {
      name = "gcs_cache"
      gcs {
        bucket    = google_storage_bucket.paperoni_cache.name
        read_only = false
      }
    }

    volumes {
      name = "gcs_config"
      gcs {
        bucket    = google_storage_bucket.paperoni_config.name
        read_only = false
      }
    }
  }
  lifecycle { ignore_changes = [template[0].containers[0].image] }
  deletion_protection = false
}

##############
# Scrape Job #
##############

resource "google_cloud_run_v2_job" "paperoni_scrape" {
  name     = "paperoni-scrape"
  location = var.google_region

  template {
    template {
      service_account = google_service_account.paperoni_user.email
      timeout         = "36000s" # 10 hours

      containers {
        image   = "gcr.io/cloudrun/hello"
        command = ["scrape"]

        resources {
          limits = {
            memory = "2Gi"
          }
        }

        env {
          name  = "GIFNOC_FILE"
          value = "/paperoni-config/paperoni.yaml"
        }

        env {
          name = "SERIEUX_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.serieux_password.id
              version = "latest"
            }
          }
        }

        env {
          name  = "MONGODB_NAME"
          value = google_firestore_database.paperoni_db.name
        }

        env {
          name  = "MONGODB_CONNECTION"
          value = local.mongo_uri
        }

        volume_mounts {
          name       = "gcs_cache"
          mount_path = "/paperoni-cache"
        }

        volume_mounts {
          name       = "gcs_config"
          mount_path = "/paperoni-config"
        }
      }

      volumes {
        name = "gcs_cache"
        gcs {
          bucket    = google_storage_bucket.paperoni_cache.name
          read_only = false
        }
      }

      volumes {
        name = "gcs_config"
        gcs {
          bucket    = google_storage_bucket.paperoni_config.name
          read_only = false
        }
      }
    }
  }
  lifecycle { ignore_changes = [template[0].template[0].containers[0].image] }
  deletion_protection = false
}

resource "google_cloud_scheduler_job" "paperoni_scrape_regular" {
  name             = "paperoni-scrape-regular"
  description      = "Execute paperoni scrape job"
  schedule         = "0 3 * * *"
  time_zone        = var.timezone
  region           = var.google_region
  attempt_deadline = "60s"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.google_region}/jobs/${google_cloud_run_v2_job.paperoni_scrape.name}:run"

    oauth_token {
      service_account_email = "${data.google_project.paperoni.number}-compute@developer.gserviceaccount.com"
    }
  }

  depends_on = [
    google_project_service.cloud_scheduler,
    google_cloud_run_v2_job_iam_member.paperoni_scrape_invoker
  ]
}
