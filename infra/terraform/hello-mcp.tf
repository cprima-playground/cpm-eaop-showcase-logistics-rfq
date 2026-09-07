# spikes/hello-mcp, deployed via `gcloud run deploy --source` (not
# Terraform originally). Config below generated from live state via
# `terraform plan -generate-config-out`, then reviewed - not hand-written.
resource "google_cloud_run_v2_service" "hello_mcp" {
  annotations          = {}
  client               = "gcloud"
  client_version       = "576.0.0"
  custom_audiences     = []
  default_uri_disabled = false
  deletion_policy      = "DELETE"
  deletion_protection  = false
  description          = null
  iap_enabled          = false
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = false
  labels               = {}
  launch_stage         = "GA"
  location             = "us-central1"
  name                 = "hello-mcp"
  project              = "cpm-geap-2026"
  tags                 = null
  build_config {
    base_image               = null
    enable_automatic_updates = false
    environment_variables    = {}
    function_target          = null
    image_uri                = "us-central1-docker.pkg.dev/cpm-geap-2026/cloud-run-source-deploy/hello-mcp"
    service_account          = null
    source_location          = "gs://run-sources-cpm-geap-2026-us-central1/services/hello-mcp/1785508518.37984-72ca2c31f9ad4818a49d645e20ff065c.zip#1785508519804010"
    worker_pool              = null
  }
  scaling {
    manual_instance_count = 0
    max_instance_count    = 20
    min_instance_count    = 0
    scaling_mode          = null
  }
  template {
    annotations                      = {}
    encryption_key                   = null
    execution_environment            = null
    gpu_zonal_redundancy_disabled    = false
    health_check_disabled            = false
    labels                           = {}
    max_instance_request_concurrency = 80
    revision                         = null
    service_account                  = "200607526455-compute@developer.gserviceaccount.com"
    session_affinity                 = false
    timeout                          = "300s"
    containers {
      args           = []
      base_image_uri = null
      command        = []
      depends_on     = []
      image          = "us-central1-docker.pkg.dev/cpm-geap-2026/cloud-run-source-deploy/hello-mcp@sha256:11027e4a7bb1bd44c9752f1a224babaf3c586020419b31133b469a409b58e5e9"
      name           = null
      working_dir    = null
      ports {
        container_port = 8080
        name           = "http1"
      }
      resources {
        cpu_idle = true
        limits = {
          cpu    = "1000m"
          memory = "512Mi"
        }
        startup_cpu_boost = true
      }
      startup_probe {
        failure_threshold     = 1
        initial_delay_seconds = 0
        period_seconds        = 240
        timeout_seconds       = 240
        tcp_socket {
          port = 8080
        }
      }
    }
  }
  traffic {
    percent  = 100
    revision = null
    tag      = null
    type     = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }
}

# __generated__ by Terraform from "projects/cpm-geap-2026/locations/us-central1/services/hello-mcp roles/run.invoker allUsers"
resource "google_cloud_run_v2_service_iam_member" "hello_mcp_public" {
  location = "us-central1"
  member   = "allUsers"
  name     = "projects/cpm-geap-2026/locations/us-central1/services/hello-mcp"
  project  = "cpm-geap-2026"
  role     = "roles/run.invoker"
}
