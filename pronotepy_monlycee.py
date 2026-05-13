# From https://github.com/Alg0v/pronotepy_monlycee

import typing
import logging

import requests
from bs4 import BeautifulSoup
from functools import partial

from pronotepy import ENTLoginError

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:73.0) Gecko/20100101 Firefox/73.0"
}


@typing.no_type_check
def _monlycee_net(
    username: str,
    password: str,
    url: str = "https://psn.monlycee.net",
    ent_cookies: typing.Union[dict, list] = None,
    **opts: str,
) -> requests.cookies.RequestsCookieJar:
    """
    ENT for monlycee.net with the new website

    Parameters
    ----------
    username : str
        username
    password : str
        password
    url: str
        url of the ent login page

    Returns
    -------
    cookies : cookies
        returns the ent session cookies
    """
    if not url:
        raise ENTLoginError("Login URL is missing")

    if not password:
        raise ENTLoginError("Password is missing")

    if not username:
        raise ENTLoginError("Username is missing")

    print(f"[ENT {url}] Logging in with {username}")

    def _log_response(resp, *args, **kwargs):
        log.debug(f"--- HTTP Response from {resp.url} ---")
        log.debug(f"Status: {resp.status_code}")
        log.debug(f"Body:\n{resp.text}\n{'-'*40}")

    # ENT Connection
    with requests.Session() as session:
        session.hooks["response"].append(_log_response)

        if ent_cookies:
            if isinstance(ent_cookies, list):
                for c in ent_cookies:
                    session.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path"))
            elif isinstance(ent_cookies, dict):
                session.cookies.update(ent_cookies)

        response = session.get(url, headers=HEADERS)
        soup = BeautifulSoup(response.text, "html.parser")
        
        form = soup.find(id="kc-form-login")
        otp_form = soup.find(id="kc-otp-login-form")

        if form is None and otp_form is None:
            print(f"[ENT {url}] Re-using existing session")
            return session.cookies

        if form is not None:
            payload = {"username": username, "password": password}
            r = session.post(form.get("action"), data=payload, headers=HEADERS)

            soup = BeautifulSoup(r.text, "html.parser")
            username_input = soup.find(id="username")
            if username_input is not None and username_input.get("aria-invalid") == "true":
                raise ENTLoginError("Username / Password is invalid")
                
            otp_form = soup.find(id="kc-otp-login-form")

        if otp_form is not None:
            print("[ENT 2FA] This device is not trusted. A 6-digit code has been sent to your email.")
            code = input("Please enter the 6-digit code: ")
            
            payload = {"emailCode": code.strip()}
            action_url = otp_form.get("action")
            
            print("[ENT] Submitting code...")
            r = session.post(action_url, data=payload, headers=HEADERS)
            soup = BeautifulSoup(r.text, "html.parser")
            
            if soup.find(id="kc-otp-login-form"):
                raise ENTLoginError("Email code is invalid")

        # Handle Keycloak Trusted Device registration
        trusted_device_form = soup.find(id="kc-form-trusted-device-name")
        if trusted_device_form:
            action = trusted_device_form.get("action")
            payload = {
                "trusted-device-name": "LVSconnect",
                "trusted-device": "yes"
            }
            print("[ENT] Registering this device as 'LVSconnect' to prevent future 2FA prompts...")
            r = session.post(action, data=payload, headers=HEADERS)
            soup = BeautifulSoup(r.text, "html.parser")

        # Handle intermediary auto-submit forms (SAML, etc)
        for _ in range(5):
            form = soup.find("form")
            if not form:
                break
                
            # Do not auto-submit if the form requires text input
            if form.find("input", type="text") or form.find("input", type="password"):
                break

            action = form.get("action")
            if not action:
                break

            payload = {}
            submit_found = False
            for tag in form.find_all(["input", "button"]):
                name = tag.get("name")
                if not name:
                    continue
                tag_type = tag.get("type", "submit" if tag.name == "button" else "text").lower()
                
                if tag_type == "hidden":
                    payload[name] = tag.get("value", "")
                elif tag_type in ["submit", "button"]:
                    if not submit_found:
                        payload[name] = tag.get("value", "")
                        submit_found = True

            print(f"[ENT] Following intermediary form to {action}")
            r = session.post(action, data=payload, headers=HEADERS)
            soup = BeautifulSoup(r.text, "html.parser")

        # Save final html to help with further debugging if it still fails
        with open("pronotepy_debug_monlycee_final.html", "w", encoding="utf-8") as f:
            f.write(soup.prettify())

        return session.cookies


ile_de_france = partial(_monlycee_net)
monlycee = partial(_monlycee_net)
monlycee_net = partial(_monlycee_net)
