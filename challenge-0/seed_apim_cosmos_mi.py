import os
from urllib.parse import urlparse

# Load .env file if running from Windows Python (via WSL)
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not available, rely on environment

from azure.identity import AzureCliCredential
from azure.mgmt.apimanagement import ApiManagementClient
from azure.mgmt.apimanagement.models import (
        ApiCreateOrUpdateParameter,
        OperationContract,
        ParameterContract,
        Protocol,
        PolicyContract,
        ResponseContract,
)


def require_env(name: str) -> str:
        value = os.environ.get(name)
        if not value:
                raise RuntimeError(f"Missing environment variable: {name}")
        return value


sub_id = require_env("AZURE_SUBSCRIPTION_ID")
rg = require_env("RESOURCE_GROUP")
service = require_env("APIM_NAME")
cosmos_endpoint = require_env("COSMOS_ENDPOINT")  # e.g. https://<account>.documents.azure.com/

# Parse and normalize Cosmos endpoint
parsed = urlparse(cosmos_endpoint)
if not parsed.scheme or not parsed.hostname:
        raise RuntimeError(f"Invalid COSMOS_ENDPOINT: {cosmos_endpoint}")

cosmos_endpoint = f"{parsed.scheme}://{parsed.hostname}/"
# MI resource must be origin without port, slash, or path
resource_attr = f"{parsed.scheme}://{parsed.hostname}"

print(f"ℹ️  Cosmos endpoint: {cosmos_endpoint}")
print(f"ℹ️  MI resource: {resource_attr}")


def policy_query_all(collection: str) -> str:
        return (
                f"""
<policies>
    <inbound>
        <base />
        <set-variable name=\"requestDateString\" value=\"@(DateTime.UtcNow.ToString(&quot;r&quot;))\" />
        <authentication-managed-identity resource=\"{resource_attr}\" output-token-variable-name=\"msi-access-token\" ignore-error=\"false\" />
        <send-request mode=\"new\" response-variable-name=\"cosmosResponse\" timeout=\"30\">
            <set-url>@(\"{cosmos_endpoint}\" + \"dbs/FactoryOpsDB/colls/{collection}/docs\")</set-url>
            <set-method>POST</set-method>
            <set-header name=\"Authorization\" exists-action=\"override\">
                <value>@(\"type=aad&amp;ver=1.0&amp;sig=\" + (string)context.Variables[\"msi-access-token\"])</value>
            </set-header>
            <set-header name=\"x-ms-date\" exists-action=\"override\">
                <value>@(context.Variables.GetValueOrDefault&lt;string&gt;(\"requestDateString\"))</value>
            </set-header>
            <set-header name=\"x-ms-version\" exists-action=\"override\"><value>2018-12-31</value></set-header>
            <set-header name=\"x-ms-documentdb-isquery\" exists-action=\"override\"><value>true</value></set-header>
            <set-header name=\"x-ms-documentdb-query-enablecrosspartition\" exists-action=\"override\"><value>true</value></set-header>
            <set-header name=\"Content-Type\" exists-action=\"override\"><value>application/query+json</value></set-header>
            <set-header name=\"Accept\" exists-action=\"override\"><value>application/json</value></set-header>
            <set-body>@{{
                return JsonConvert.SerializeObject(new {{
                    query = \"SELECT * FROM c\",
                    parameters = new object[0]
                }});
            }}</set-body>
        </send-request>
        <choose>
            <when condition=\"@(((IResponse)context.Variables[&quot;cosmosResponse&quot;]).StatusCode == 200)\">
                <return-response>
                    <set-status code=\"200\" reason=\"OK\" />
                    <set-header name=\"Content-Type\" exists-action=\"override\"><value>application/json</value></set-header>
                    <set-body>@{{
                        var response = ((IResponse)context.Variables[\"cosmosResponse\"]).Body.As&lt;JObject&gt;();
                        return response[\"Documents\"].ToString();
                    }}</set-body>
                </return-response>
            </when>
            <otherwise>
                <return-response>
                    <set-status code=\"502\" reason=\"Cosmos DB Query Failed\" />
                    <set-header name=\"Content-Type\" exists-action=\"override\"><value>application/json</value></set-header>
                    <set-body>@{{ return ((IResponse)context.Variables[\"cosmosResponse\"]).Body.As&lt;string&gt;(); }}</set-body>
                </return-response>
            </otherwise>
        </choose>
    </inbound>
    <backend><base /></backend>
    <outbound><base /></outbound>
    <on-error><base /></on-error>
</policies>
"""
        ).strip()


def policy_query_by_id(collection: str, param_name: str, field: str) -> str:
        return (
                f"""
<policies>
    <inbound>
        <base />
        <set-variable name=\"requestDateString\" value=\"@(DateTime.UtcNow.ToString(&quot;r&quot;))\" />
        <authentication-managed-identity resource=\"{resource_attr}\" output-token-variable-name=\"msi-access-token\" ignore-error=\"false\" />
        <set-variable name=\"{param_name}\" value=\"@(context.Request.MatchedParameters[&quot;{param_name}&quot;])\" />
        <send-request mode=\"new\" response-variable-name=\"cosmosResponse\" timeout=\"30\">
            <set-url>@(\"{cosmos_endpoint}\" + \"dbs/FactoryOpsDB/colls/{collection}/docs\")</set-url>
            <set-method>POST</set-method>
            <set-header name=\"Authorization\" exists-action=\"override\">
                <value>@(\"type=aad&amp;ver=1.0&amp;sig=\" + (string)context.Variables[\"msi-access-token\"])</value>
            </set-header>
            <set-header name=\"x-ms-date\" exists-action=\"override\">
                <value>@(context.Variables.GetValueOrDefault&lt;string&gt;(\"requestDateString\"))</value>
            </set-header>
            <set-header name=\"x-ms-version\" exists-action=\"override\"><value>2018-12-31</value></set-header>
            <set-header name=\"x-ms-documentdb-isquery\" exists-action=\"override\"><value>true</value></set-header>
            <set-header name=\"x-ms-documentdb-query-enablecrosspartition\" exists-action=\"override\"><value>true</value></set-header>
            <set-header name=\"Content-Type\" exists-action=\"override\"><value>application/query+json</value></set-header>
            <set-header name=\"Accept\" exists-action=\"override\"><value>application/json</value></set-header>
            <set-body>@{{
                string v = context.Variables[\"{param_name}\"] as string;
                return JsonConvert.SerializeObject(new {{
                    query = \"SELECT * FROM c WHERE c.{field} = @{param_name}\",
                    parameters = new object[] {{ new {{ name = \"@{param_name}\", value = v }} }}
                }});
            }}</set-body>
        </send-request>
        <choose>
            <when condition=\"@(((IResponse)context.Variables[&quot;cosmosResponse&quot;]).StatusCode == 200)\">
                <return-response>
                    <set-status code=\"200\" reason=\"OK\" />
                    <set-header name=\"Content-Type\" exists-action=\"override\"><value>application/json</value></set-header>
                    <set-body>@{{
                        var response = ((IResponse)context.Variables[\"cosmosResponse\"]).Body.As&lt;JObject&gt;();
                        var docs = response[\"Documents\"] as JArray;
                        return docs.Count > 0 ? docs[0].ToString() : JsonConvert.SerializeObject(new {{ error = \"not found\" }});
                    }}</set-body>
                </return-response>
            </when>
            <otherwise>
                <return-response>
                    <set-status code=\"502\" reason=\"Cosmos DB Query Failed\" />
                    <set-header name=\"Content-Type\" exists-action=\"override\"><value>application/json</value></set-header>
                    <set-body>@{{ return ((IResponse)context.Variables[\"cosmosResponse\"]).Body.As&lt;string&gt;(); }}</set-body>
                </return-response>
            </otherwise>
        </choose>
    </inbound>
    <backend><base /></backend>
    <outbound><base /></outbound>
    <on-error><base /></on-error>
</policies>
"""
        ).strip()


cred = AzureCliCredential()
client = ApiManagementClient(cred, sub_id)


def create_api(api_id: str, display_name: str, description: str, path: str):
        client.api.begin_create_or_update(
                rg,
                service,
                api_id,
                ApiCreateOrUpdateParameter(
                        display_name=display_name,
                        description=description,
                        path=path,
                        protocols=[Protocol.https],
                        subscription_required=True,
                ),
        ).result()


print("📡 Creating Machine API...")
machine_api_id = "machine-api"
create_api(
        machine_api_id,
        display_name="Machine API",
        description="Machines via Cosmos DB (APIM Managed Identity)",
        path="machine",
)

print("📡 Creating List Machines operation...")
client.api_operation.create_or_update(
        rg,
        service,
        machine_api_id,
        "list-machines",
        OperationContract(
                display_name="List Machines",
                description="Retrieves all machines from the factory operations database.",
                method="GET",
                url_template="/",
                template_parameters=[],
                responses=[ResponseContract(status_code=200, description="OK")],
        ),
)
client.api_operation_policy.create_or_update(
        rg,
        service,
        machine_api_id,
        "list-machines",
        "policy",
        parameters=PolicyContract(value=policy_query_all("Machines"), format="rawxml"),
)

print("📡 Creating Get Machine operation...")
client.api_operation.create_or_update(
        rg,
        service,
        machine_api_id,
        "get-machine",
        OperationContract(
                display_name="Get Machine",
                description="Retrieves a specific machine by its unique identifier.",
                method="GET",
                url_template="/{id}",
                template_parameters=[ParameterContract(name="id", type="string", required=True)],
                responses=[
                        ResponseContract(status_code=200, description="OK"),
                        ResponseContract(status_code=404, description="Not Found"),
                ],
        ),
)
client.api_operation_policy.create_or_update(
        rg,
        service,
        machine_api_id,
        "get-machine",
        "policy",
        parameters=PolicyContract(value=policy_query_by_id("Machines", "id", "id"), format="rawxml"),
)

print("✅ APIM Machine API deployed: path=/machine (Cosmos via Managed Identity)")


print("📡 Creating Maintenance API...")
maintenance_api_id = "maintenance-api"
create_api(
        maintenance_api_id,
        display_name="Maintenance API",
        description="Thresholds via Cosmos DB (APIM Managed Identity)",
        path="maintenance",
)

print("📡 Creating List Thresholds operation...")
client.api_operation.create_or_update(
        rg,
        service,
        maintenance_api_id,
        "list-thresholds",
        OperationContract(
                display_name="List Thresholds",
                description="Retrieves all operational thresholds for factory equipment.",
                method="GET",
                url_template="/",
                template_parameters=[],
                responses=[ResponseContract(status_code=200, description="OK")],
        ),
)
client.api_operation_policy.create_or_update(
        rg,
        service,
        maintenance_api_id,
        "list-thresholds",
        "policy",
        parameters=PolicyContract(value=policy_query_all("Thresholds"), format="rawxml"),
)

print("📡 Creating Get Threshold operation...")
client.api_operation.create_or_update(
        rg,
        service,
        maintenance_api_id,
        "get-threshold",
        OperationContract(
                display_name="Get Threshold",
                description="Retrieves operational thresholds for a specific machine type.",
                method="GET",
                url_template="/{machineType}",
                template_parameters=[ParameterContract(name="machineType", type="string", required=True)],
                responses=[
                        ResponseContract(status_code=200, description="OK"),
                        ResponseContract(status_code=404, description="Not Found"),
                ],
        ),
)
client.api_operation_policy.create_or_update(
        rg,
        service,
        maintenance_api_id,
        "get-threshold",
        "policy",
        parameters=PolicyContract(
                value=policy_query_by_id("Thresholds", "machineType", "machineType"),
                format="rawxml",
        ),
)

print("✅ APIM Maintenance API deployed: path=/maintenance (Cosmos via Managed Identity)")
