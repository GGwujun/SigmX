# SigmX Data Hub Python SDK

```bash
pip install ./datahub-python
export SIGMX_DATAHUB_KEY=sxd_live_...
sigmx-data get /api/v1/stocks/daily --param symbol=600519.SH --param limit=100
```

```python
import os
from sigmx_datahub import DataHubClient

client = DataHubClient(os.environ["SIGMX_DATAHUB_KEY"])
result = client.stocks_daily("600519.SH", limit=100)
print(result.data)
print(result.request_id, result.credits_charged, result.credits_remaining)
```

The SDK never stores the Credential. Use environment variables or an external secret manager; do not commit Credentials to source control.
