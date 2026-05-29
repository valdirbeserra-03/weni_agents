from http.cookies import SimpleCookie
import re

import requests

from weni import Tool
from weni.context import Context
from weni.responses import TextResponse


COOKIE_FIELD_MAP = {
    "_vss": "vss_cookie",
}

START_LOGIN_URL = (
    "https://brastemp.myvtex.com/api/vtexid/pub/authentication/startlogin"
)
SEND_ACCESS_KEY_URL = (
    "https://brastemp.myvtex.com/api/vtexid/pub/authentication/accesskey/send"
)
ACCOUNT_NAME = "brastemp"
SCOPE = "brastemp"
CALLBACK_URL = (
    "https://www.brastemp.myvtex.com/api/vtexid/oauth/finish?popup=false"
)
RETURN_URL = "https://www.brastemp.myvtex.com"
LOCALE = "pt-BR"


class StartAuthentication(Tool):
    def execute(self, context: Context) -> TextResponse:
        email_user = context.parameters.get("email_user", "").strip()

        if not self.is_valid_email(email_user):
            return TextResponse(data={"error": "E-mail inválido"})

        start_login_response = self.start_login(
            start_login_url=START_LOGIN_URL,
            account_name=ACCOUNT_NAME,
            scope=SCOPE,
            callback_url=CALLBACK_URL,
            return_url=RETURN_URL,
            email_user=email_user,
        )

        if start_login_response.get("error"):
            return TextResponse(data=start_login_response)

        cookies = start_login_response.get("cookies", {})
        access_key_response = self.send_access_key(
            send_access_key_url=SEND_ACCESS_KEY_URL,
            email_user=email_user,
            locale=LOCALE,
            cookies=cookies,
        )

        if access_key_response.get("cookies"):
            cookies.update(access_key_response["cookies"])

        if access_key_response.get("error"):
            return TextResponse(data=access_key_response)

        contact_fields_status = self.save_contact_fields(
            context=context, email_user=email_user, cookies=cookies
        )

        return TextResponse(
            data={
                "status": "access_key_sent",
                "email_user": email_user,
                "vss_cookie": cookies.get("_vss", ""),
                "message": "Código de acesso enviado para o e-mail informado",
                "saved_contact_fields": self.contact_field_names(cookies),
                "cookies_found": list(cookies.keys()),
                "contact_fields_status": contact_fields_status,
            }
        )

    def start_login(
        self,
        start_login_url: str,
        account_name: str,
        scope: str,
        callback_url: str,
        return_url: str,
        email_user: str,
    ) -> dict:
        files = {
            "accountName": (None, account_name),
            "scope": (None, scope),
            "callbackUrl": (None, callback_url),
            "returnUrl": (None, return_url),
            "user": (None, email_user),
        }

        try:
            response = requests.post(
                start_login_url, files=files, timeout=15
            )
            response.raise_for_status()
            cookies = self.extract_cookies(response, COOKIE_FIELD_MAP.keys())
            return {"cookies": cookies, "response": self.safe_json(response)}
        except requests.exceptions.HTTPError as error:
            response = error.response
            status_code = response.status_code if response is not None else None
            response_body = response.text[:500] if response is not None else ""
            print(f"HTTP error starting VTEX login: {status_code} - {response_body}")
            return {
                "error": "Não foi possível iniciar a autenticação",
                "step": "start_login",
                "status_code": status_code,
                "response_body": response_body,
            }
        except requests.exceptions.RequestException as error:
            print(f"Error starting VTEX login: {error}")
            return {
                "error": "Não foi possível iniciar a autenticação",
                "step": "start_login",
                "details": str(error),
            }

    def send_access_key(
        self,
        send_access_key_url: str,
        email_user: str,
        locale: str,
        cookies: dict,
    ) -> dict:
        headers = {
            "Cookie": self.build_cookie_header(cookies, ["_vss"]),
        }
        files = {
            "locale": (None, locale),
            "email": (None, email_user),
        }

        try:
            response = requests.post(
                send_access_key_url, headers=headers, files=files, timeout=15
            )
            response.raise_for_status()
            return {
                "cookies": self.extract_cookies(response, COOKIE_FIELD_MAP.keys()),
                "response": self.safe_json(response),
            }
        except requests.exceptions.HTTPError as error:
            response = error.response
            status_code = response.status_code if response is not None else None
            response_body = response.text[:500] if response is not None else ""
            print(f"HTTP error sending VTEX access key: {status_code} - {response_body}")
            return {
                "error": "Não foi possível enviar o código de acesso",
                "step": "send_access_key",
                "status_code": status_code,
                "response_body": response_body,
            }
        except requests.exceptions.RequestException as error:
            print(f"Error sending VTEX access key: {error}")
            return {
                "error": "Não foi possível enviar o código de acesso",
                "step": "send_access_key",
                "details": str(error),
            }

    def save_contact_fields(self, context: Context, email_user: str, cookies: dict) -> dict:
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

        fields = {"email_user": email_user}
        fields.update(
            {
                field_name: cookie_value
                for cookie_name, field_name in COOKIE_FIELD_MAP.items()
                if (cookie_value := cookies.get(cookie_name))
            }
        )

        field_creation_statuses = []
        for key, label in {
            "email_user": "emailUser",
            "vss_cookie": "_vss",
        }.items():
            if key in fields:
                field_status = self.ensure_contact_field(
                    auth_token=auth_token, key=key, label=label
                )
                field_creation_statuses.append(field_status)

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
                "field_creation_statuses": field_creation_statuses,
                "status_code": response.status_code,
            }
        except requests.exceptions.HTTPError as error:
            response = error.response
            status_code = response.status_code if response is not None else None
            response_body = response.text[:500] if response is not None else ""
            print(f"HTTP error saving authentication contact fields: {status_code} - {response_body}")
            return {
                "saved": False,
                "step": "save_contact_fields",
                "status_code": status_code,
                "response_body": response_body,
            }
        except requests.exceptions.RequestException as error:
            print(f"Error saving authentication contact fields: {error}")
            return {
                "saved": False,
                "step": "save_contact_fields",
                "details": str(error),
            }

    def ensure_contact_field(self, auth_token: str, key: str, label: str) -> dict:
        try:
            response = requests.post(
                "https://flows.weni.ai/api/v2/fields.json",
                headers={
                    "Authorization": f"Token {auth_token}",
                    "Content-Type": "application/json",
                },
                params={"key": key},
                json={"label": label, "value_type": "text"},
                timeout=15,
            )
            response.raise_for_status()
            return {
                "created": True,
                "key": key,
                "status_code": response.status_code,
            }
        except requests.exceptions.HTTPError as error:
            response = error.response
            status_code = response.status_code if response is not None else None
            response_body = response.text[:500] if response is not None else ""
            print(f"HTTP error ensuring contact field {key}: {status_code} - {response_body}")
            return {
                "created": False,
                "step": "ensure_contact_field",
                "key": key,
                "status_code": status_code,
                "response_body": response_body,
            }
        except requests.exceptions.RequestException as error:
            print(f"Error ensuring contact field {key}: {error}")
            return {
                "created": False,
                "step": "ensure_contact_field",
                "key": key,
                "details": str(error),
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

    def contact_field_names(self, cookies: dict) -> list[str]:
        fields = ["email_user"]
        fields.extend(
            field_name
            for cookie_name, field_name in COOKIE_FIELD_MAP.items()
            if cookies.get(cookie_name)
        )
        return fields

    def safe_json(self, response: requests.Response):
        try:
            return response.json()
        except ValueError:
            return {"status_code": response.status_code}

    def is_valid_email(self, email_user: str) -> bool:
        return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_user))
