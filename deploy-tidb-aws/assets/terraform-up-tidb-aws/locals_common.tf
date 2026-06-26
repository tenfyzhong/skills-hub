locals {
  namespace   = "tidb-cluster"
  n_pd        = 1
  n_tidb      = 3
  n_tikv      = 3
  n_tiflash   = 1
  n_ticdc     = 3
  cdc_newarch = true
  username    = "ubuntu"

  extra_services = {}
}
