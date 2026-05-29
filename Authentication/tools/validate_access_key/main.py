from http.cookies import SimpleCookie

import requests

from weni import Tool
from weni.context import Context
from weni.responses import TextResponse


COOKIE_FIELD_MAP = {
    "_vss": "vss_cookie",
}

VALIDATE_ACCESS_KEY_URL = (
    "https://brastemp.myvtex.com/api/vtexid/pub/authentication/accesskey/validate"
)


class ValidateAccessKey(Tool):
    def execute(self, context: Context) -> TextResponse:
        access_key = (
            context.parameters.get("acesskey", "")
            or context.parameters.get("accesskey", "")
            or context.parameters.get("access_key", "")
        )
        access_key = str(access_key).strip()

        if not access_key:
            return TextResponse(data={"error": "Código de acesso não informado"})

        email_user = (
            self.get_contact_value(context, "email_user")
            or context.parameters.get("email_user", "")
        )
        cookies = {
            cookie_name: (
                self.get_contact_value(context, field_name)
                or context.parameters.get(field_name, "")
            )
            for cookie_name, field_name in COOKIE_FIELD_MAP.items()
        }

        if not email_user or not all(cookies.values()):
            contact_fields = self.fetch_contact_fields(context)
            if contact_fields:
                email_user = email_user or self.get_field_value(
                    contact_fields, "email_user"
                )
                for cookie_name, field_name in COOKIE_FIELD_MAP.items():
                    cookies[cookie_name] = cookies.get(cookie_name) or self.get_field_value(
                        contact_fields, field_name
                    ) or self.get_field_value(contact_fields, cookie_name)
        email_user = str(email_user).strip()

        if not email_user:
            return TextResponse(
                data={
                    "error": "E-mail não encontrado no contato. Reinicie a autenticação",
                    "debug": self.context_debug(context),
                }
            )

        required_cookies = ["_vss"]
        missing_cookies = [
            cookie_name for cookie_name in required_cookies if not cookies.get(cookie_name)
        ]
        if missing_cookies:
            return TextResponse(
                data={
                    "error": "Cookies de autenticação não encontrados. Reinicie a autenticação",
                    "missing_cookies": missing_cookies,
                    "debug": self.context_debug(context),
                }
            )

        validation_response = self.validate_access_key(
            validate_access_key_url=VALIDATE_ACCESS_KEY_URL,
            access_key=access_key,
            email_user=email_user,
            cookies=cookies,
        )
        validation_response["debug"] = {
            "email_user_found": bool(email_user),
            "cookies_found": [
                cookie_name for cookie_name, cookie_value in cookies.items() if cookie_value
            ],
            "access_key_length": len(access_key),
        }

        if validation_response.get("cookies"):
            validation_response["contact_fields_status"] = self.save_contact_fields(
                context=context, cookies=validation_response["cookies"]
            )

        return TextResponse(data=validation_response)

    def validate_access_key(
        self,
        validate_access_key_url: str,
        access_key: str,
        email_user: str,
        cookies: dict,
    ) -> dict:
        headers = {
            "Cookie": self.build_cookie_header(cookies, ["_vss"]),
        }
        files = {
            "accesskey": (None, access_key),
            "login": (None, email_user),
        }

        try:
            response = requests.post(
                validate_access_key_url, headers=headers, files=files, timeout=15
            )
            response.raise_for_status()
            return {
                "status": "authenticated",
                "message": "Código de acesso validado com sucesso",
                "cookies": self.extract_cookies(response, COOKIE_FIELD_MAP.keys()),
                "response": self.safe_json(response),
            }
        except requests.exceptions.HTTPError as error:
            status = error.response.status_code if error.response is not None else None
            response_body = error.response.text[:500] if error.response is not None else ""
            print(f"HTTP error validating VTEX access key: {error}")
            return {
                "error": "Código de acesso inválido ou expirado",
                "step": "validate_access_key",
                "status_code": status,
                "response_body": response_body,
            }
        except requests.exceptions.RequestException as error:
            print(f"Error validating VTEX access key: {error}")
            return {
                "error": "Não foi possível validar o código de acesso",
                "step": "validate_access_key",
                "details": str(error),
            }

    def save_contact_fields(self, context: Context, cookies: dict) -> dict:
        contact_urn = context.contact.get("urn", "")
        auth_token = (
            context.project.get("auth_token", "")
            or context.credentials.get("WENI_TOKEN", "")
        )

        if not contact_urn or not auth_token:
            print("Contact URN or project auth token not available")
            return {
                "saved": False,
                "reason": "missing_contact_urn_or_weni_token",
                "has_contact_urn": bool(contact_urn),
                "has_weni_token": bool(auth_token),
            }

        fields = {
            field_name: cookie_value
            for cookie_name, field_name in COOKIE_FIELD_MAP.items()
            if (cookie_value := cookies.get(cookie_name))
        }

        if not fields:
            return {"saved": False, "reason": "no_cookies_to_save"}

        try:
            response = requests.post(
                "https://flows.weni.ai/api/v2/contacts.json",
                headers={
                    "Authorization": f"Token {auth_token}",
                    "Content-Type": "application/json",
                },
                params={"urn": contact_urn},
                json={"fields": fields},
                timeout=15,
            )
            response.raise_for_status()
            return {
                "saved": True,
                "fields": list(fields.keys()),
                "status_code": response.status_code,
            }
        except requests.exceptions.HTTPError as error:
            response = error.response
            status_code = response.status_code if response is not None else None
            response_body = response.text[:500] if response is not None else ""
            print(f"HTTP error saving validated authentication cookies: {status_code} - {response_body}")
            return {
                "saved": False,
                "step": "save_contact_fields",
                "status_code": status_code,
                "response_body": response_body,
            }
        except requests.exceptions.RequestException as error:
            print(f"Error saving validated authentication cookies: {error}")
            return {
                "saved": False,
                "step": "save_contact_fields",
                "details": str(error),
            }

    def get_contact_value(self, context: Context, key: str) -> str:
        value = context.contact.get(key, "")
        if value:
            return value

        fields = context.contact.get("fields", {})
        if isinstance(fields, dict):
            return self.get_field_value(fields, key)

        return ""

    def fetch_contact_fields(self, context: Context) -> dict:
        contact_urn = context.contact.get("urn", "")
        auth_token = (
            context.project.get("auth_token", "")
            or context.credentials.get("WENI_TOKEN", "")
        )

        if not contact_urn or not auth_token:
            return {}

        try:
            response = requests.get(
                "https://flows.weni.ai/api/v2/contacts.json",
                headers={
                    "Authorization": f"Token {auth_token}",
                    "Content-Type": "application/json",
                },
                params={"urn": contact_urn},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            contacts = data.get("results", []) if isinstance(data, dict) else []
            if not contacts:
                return {}
            fields = contacts[0].get("fields", {})
            return fields if isinstance(fields, dict) else {}
        except requests.exceptions.RequestException as error:
            print(f"Error fetching contact fields: {error}")
            return {}

    def get_field_value(self, fields: dict, key: str) -> str:
        field_value = fields.get(key, "")
        if not field_value:
            field_value = fields.get(key.lower(), "")
        if isinstance(field_value, dict):
            return (
                field_value.get("value", "")
                or field_value.get("text", "")
                or field_value.get("string", "")
                or field_value.get("display", "")
            )
        return field_value or ""

    def context_debug(self, context: Context) -> dict:
        return {
            "has_contact_urn": bool(context.contact.get("urn", "")),
            "has_contact_fields": bool(context.contact.get("fields", {})),
            "has_weni_token": bool(
                context.project.get("auth_token", "")
                or context.credentials.get("WENI_TOKEN", "")
            ),
        }

    def extract_cookies(self, response: requests.Response, cookie_names) -> dict:
        cookies = {
            cookie.name: cookie.value
            for cookie in response.cookies
            if cookie.name in cookie_names
        }

        headers = []
        raw_headers = getattr(response.raw, "headers", None)
        if raw_headers and hasattr(raw_headers, "get_all"):
            headers.extend(raw_headers.get_all("Set-Cookie") or [])
        elif response.headers.get("Set-Cookie"):
            headers.append(response.headers["Set-Cookie"])

        for header in headers:
            simple_cookie = SimpleCookie()
            simple_cookie.load(header)
            for cookie_name in cookie_names:
                if cookie_name in simple_cookie and cookie_name not in cookies:
                    cookies[cookie_name] = simple_cookie[cookie_name].value

        return cookies

    def build_cookie_header(self, cookies: dict, cookie_names: list[str]) -> str:
        return "; ".join(
            f"{cookie_name}={cookies[cookie_name]}"
            for cookie_name in cookie_names
            if cookies.get(cookie_name)
        )

    def safe_json(self, response: requests.Response):
        try:
            return response.json()
        except ValueError:
            return {"status_code": response.status_code}
