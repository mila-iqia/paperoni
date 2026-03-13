
######################
# Scrape-updates Job #
######################

resource "google_cloud_run_v2_job_iam_member" "paperoni_scrape_updates_invoker" {
  name     = google_cloud_run_v2_job.paperoni_scrape_updates.name
  location = google_cloud_run_v2_job.paperoni_scrape_updates.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_project.paperoni.number}-compute@developer.gserviceaccount.com"
}

resource "google_cloud_run_v2_job" "paperoni_scrape_updates" {
  name     = "${var.prefix}-scrape-updates"
  location = var.google_region

  template {
    template {
      service_account = google_service_account.paperoni_user.email
      timeout         = "36000s" # 10 hours

      containers {
        image   = "gcr.io/cloudrun/hello"
        command = ["scrape-updates"]

        resources {
          limits = {
            memory = "4Gi"
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

        env {
          name  = "INSTANCE_PREFIX"
          value = var.prefix
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

resource "google_cloud_scheduler_job" "paperoni_scrape_updates_regular" {
  name             = "${var.prefix}-scrape-updates-regular"
  description      = "Execute paperoni scrape-updates job"
  schedule         = "0 3 * * 1"
  time_zone        = var.timezone
  region           = var.google_region
  attempt_deadline = "60s"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.google_region}/jobs/${google_cloud_run_v2_job.paperoni_scrape_updates.name}:run"

    oauth_token {
      service_account_email = "${data.google_project.paperoni.number}-compute@developer.gserviceaccount.com"
    }
  }

  depends_on = [
    google_project_service.cloud_scheduler,
    google_cloud_run_v2_job_iam_member.paperoni_scrape_updates_invoker
  ]
}
