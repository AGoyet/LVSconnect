# From https://github.com/Alg0v/pronotepy_monlycee

import typing

import requests
from bs4 import BeautifulSoup
from functools import partial

from pronotepy import ENTLoginError

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

    # ENT Connection
    with requests.Session() as session:
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
            
            r = session.post(action_url, data=payload, headers=HEADERS)
            soup = BeautifulSoup(r.text, "html.parser")
            
            if soup.find(id="kc-otp-login-form"):
                raise ENTLoginError("Email code is invalid")

        return session.cookies


ile_de_france = partial(_monlycee_net)
monlycee = partial(_monlycee_net)
monlycee_net = partial(_monlycee_net)
