
# Ansible role to install Paperoni

## Requirements

Requires the role `pyservice` which is hosted at `https://github.com/mila-iqia/ansible-role-pyservice` (the dependency should be properly defined in the metadata).


## Inventory

Here is an example of inventory to use with this role. Set `<VARIABLE>` to its proper value. Variables marked with SECRET are secrets and should be encrypted.

```yaml
all:
  vars:
    paperoni_name: paperoni
    paperoni_user: paperoni
    paperoni_repo: https://github.com/mila-iqia/paperoni
    paperoni_tag: master

    paperoni_port: 8000       # Can override
    paperoni_host: "0.0.0.0"  # Can override

    paperoni_ssl_enabled: <WHETHER SSL IS ENABLED>
    paperoni_ssl_cert: <SSL_CERT_CONTENT (SECRET!)>
    paperoni_ssl_key: <SSL_KEY_CONTENT (SECRET!)>

    paperoni_oauth_enabled: <WHETHER OAUTH IS ENABLED>
    paperoni_google_client_id: <GOOGLE_CLIENT_ID (SECRET!)>
    paperoni_google_client_secret: <GOOGLE_CLIENT_SECRET (SECRET!)>

    paperoni_sentry_enabled: <WHETHER SENTRY IS ENABLED>
    paperoni_sentry_dsn: <SENTRY DSN (SECRET!)>
    paperoni_sentry_traces_sample_rate: <SENTRY TRACES SAMPLE RATE>
    paperoni_sentry_environment: <SENTRY ENVIRONMENT NAME>

    paperoni_token_semantic_scholar: <SEMANTIC_SCHOLAR API KEY (SECRET!)>
    paperoni_token_xplore: <XPLORE API KEY (SECRET!)>
    paperoni_token_elsevier: <ELSEVIER API KEY (SECRET!)>
    paperoni_token_springer: <SPRINGER API KEY (SECRET!)>
    paperoni_token_zeta_alpha: <ZETA_ALPHA API KEY (SECRET!)>

    paperoni_scrape_schedule: "Mon, 02:00"
    paperoni_cleanup_schedule: "Mon, 12:00"
```


## Playbook

Simple recipe for installation and reinstallation:

```
- hosts: paperoni-machine
  tasks:
  - name: Install
    become: true
    import_role:
      name: paperoni_service
```

And here's one that will deactivate the services (i.e. data scraping and server):

```
- hosts: paperoni-machine
  tasks:
  - name: Deactivate
    become: true
    import_role:
      name: paperoni_service
      tasks_from: deactivate
```
