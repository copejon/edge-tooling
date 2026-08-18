# Prerequisites

| Requirement | Components | Source |
|-------------|------------|--------|
| AWS CLI + AWS_PROFILE | EC2 Deploy, Two-Node Toolbox | AWS account configuration |
| OpenShift Pull Secret | All cluster deployments | https://console.redhat.com/openshift/create/local |
| Offline Token | SNO Deploy | https://cloud.redhat.com/openshift/token |
| SSH Keys | All components | Generate with `ssh-keygen` |
| CI Token | CI builds | https://console-openshift-console.apps.ci.l2s4.p1.openshiftapps.com |
| RHEL Subscription | EC2/hypervisor hosts | Red Hat Subscription Manager |
| Go 1.21+ | CI Tooling (`readiness-report`) | https://go.dev/dl/ |
