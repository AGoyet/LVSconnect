import datetime
import logging
from time import time
from typing import (
    List,
    Callable,
    Optional,
    Union,
    TypeVar,
    Type,
    TYPE_CHECKING,
    Tuple,
)

from Crypto.Hash import SHA256
import re
from urllib.parse import urlparse, urlunparse

from .exceptions import *
from .exceptions import MFAError
from .pronoteAPI import (
    _Communication,
    _Encryption,
    _KeepAlive,
    _enleverAlea,
    _prepare_onglets,
    log,
)
import json

if TYPE_CHECKING:
    from requests.cookies import RequestsCookieJar
    from typing_extensions import Protocol

    class ENTFunction(Protocol):
        def __call__(self, u: str, p: str, **kwargs: str) -> RequestsCookieJar:
            ...


__all__ = ("ClientBase",)

T = TypeVar("T", bound="ClientBase")


class ClientBase:
    """Base for every PRONOTE client. Provides login.

    Args:
        pronote_url (str): URL of the server
        username (str)
        password (str)
        ent (Optional[Callable]): Cookies for ENT connections
        mode (bool): internal option
        uuid (str): Your application UUID (any unique string)
        account_pin (Optional[str]): 2FA PIN to the account.

            Consider deleting it after logging in.

            .. code-block:: python

                del client.account_pin

        client_identifier (Optional[str]):
            Identificator of this client provided by PRONOTE. PRONOTE uses this
            to remember a browser / client.

        device_name (Optional[str]): A name for registering this client as a device.

    Attributes:
        start_day (datetime.datetime): The first day of the school year
        week (int): The current week of the school year
        logged_in (bool): If the user is successfully logged in
        username (str)
        password (str)
        pronote_url (str)
        info (ClientInfo): Provides information about the current client. Name etc...
        last_connection (datetime.datetime)
        client_identifier (str): Identificator of this client provided by PRONOTE
    """

    def __init__(
        self,
        pronote_url: str,
        username: str = "",
        password: str = "",
        ent: Optional["ENTFunction"] = None,
        mode: str = "normal",
        uuid: str = "",
        account_pin: Optional[str] = None,
        client_identifier: Optional[str] = None,
        device_name: Optional[str] = None,
    ) -> None:
        log.info("INIT")
        # start communication session
        if not len(password) + len(username):
            raise PronoteAPIError(
                "Please provide login credentials. Cookies are None, and username and password are empty."
            )

        self.ent = ent
        if ent:
            pronote_url = pronote_url.replace("login=true", "")
            cookies = ent(username, password, pronote_url=pronote_url)
        else:
            cookies = None

        if mode != "normal" and not uuid:
            raise PronoteAPIError("UUID must not be empty")
        self.uuid = uuid
        self.login_mode = mode

        self.username = username
        self.password = password
        self.pronote_url = pronote_url
        self.communication = _Communication(pronote_url, cookies)

        self.account_pin = account_pin
        self.client_identifier = client_identifier
        self.device_name = device_name

        self.attributes, self.func_options = self.communication.initialise(
            self.client_identifier
        )

        if not self.client_identifier:
            self.client_identifier = self.func_options["dataSec"]["data"][
                "identifiantNav"
            ]

        # set up encryption
        self.encryption = _Encryption()
        self.encryption.aes_iv = self.communication.encryption.aes_iv

        # some other attribute creation
        self._last_ping = time()

        self.parametres_utilisateur: dict = {}
        self.auth_cookie: dict = {}
        self.info: dict

        self.start_day = datetime.datetime.strptime(
            self.func_options["dataSec"]["data"]["General"]["PremierLundi"]["V"],
            "%d/%m/%Y",
        ).date()
        self.week = self.get_week(datetime.date.today())

        self._refreshing = False

        self.logged_in = self._login()
        self._expired = False

        self.last_connection: Optional[str]

    @classmethod
    def qrcode_login(
        cls: Type[T],
        qr_code: dict,
        pin: str,
        uuid: str,
        account_pin: Optional[str] = None,
        client_identifier: Optional[str] = None,
        device_name: Optional[str] = None,
        skip_2fa: bool = False,
    ) -> T:
        """Login with QR code

        The created client instance will have its username and password
        attributes set to the credentials for the next login using
        :meth:`.token_login`.

        Args:
            qr_code (dict): JSON contained in the QR code. Must have ``login``, ``jeton`` and ``url`` keys.
            pin (str): 4-digit confirmation code created during QR code setup
            uuid (str): Unique ID for your application. Must not change between logins.
            account_pin (Optional[str]): 2FA PIN to the account
            client_identifier (Optional[str]): Identificator of this client provided by PRONOTE
            device_name (Optional[str]): A name for registering this client as a device.
            skip_2fa (bool): Skip 2FA. PRONOTE will require it when connecting using the generated token (:meth:`.token_login`).
        """
        encryption = _Encryption()
        encryption.aes_set_key(pin.encode())

        short_token = bytes.fromhex(qr_code["login"])
        long_token = bytes.fromhex(qr_code["jeton"])

        try:
            login = encryption.aes_decrypt(short_token).decode()
            jeton = encryption.aes_decrypt(long_token).decode()
        except CryptoError as ex:
            raise QRCodeDecryptError("invalid confirmation code") from ex

        url = urlparse(qr_code["url"])

        # The app would query the server for all the available spaces and find
        # a space by checking if the last part of the URL matches one of the
        # space URLs. eg. "/pronote/parent.html" would match "mobile.parent.html"
        # (info url: <pronote root>/InfoMobileApp.json?id=0D264427-EEFC-4810-A9E9-346942A862A4)

        # We're gonna try the shorter route of just prepending "mobile." if it
        # isn't there already
        parts = url.path.split("/")
        if not parts[-1].startswith("mobile."):
            parts[-1] = "mobile." + parts[-1]

        # Reconstruct the url and add magic parameters at the end of the URL.
        # You can find them in a file called "ObjetCommMessage.js" in the
        # connection method when you decompile the mobile APK.
        fixed_url = url._replace(
            path="/".join(parts),
            query="fd=1&bydlg=A6ABB224-12DD-4E31-AD3E-8A39A1C2C335&login=true",
            fragment="",
        )

        client = cls(
            urlunparse(fixed_url),
            login,
            jeton,
            mode="qr_code",
            uuid=uuid,
            account_pin=account_pin,
            client_identifier=client_identifier,
            device_name=device_name,
        )
        client.login_mode = "token"  # for subsequent refreshes

        if not skip_2fa:
            # check if the account has 2FA enabled
            resp = client.post("PageInfosPerso", onglet=49)

            mode = resp["dataSec"]["data"]["securisation"].get("mode", 0)
            if mode == 0:
                log.warning("couldn't get account security mode, ignoring...")
                return client

            return cls.token_login(
                **client.export_credentials(),
                account_pin=account_pin,
                device_name=device_name,
            )

        return client

    @classmethod
    def token_login(
        cls: Type[T],
        pronote_url: str,
        username: str,
        password: str,
        uuid: str,
        account_pin: Optional[str] = None,
        client_identifier: Optional[str] = None,
        device_name: Optional[str] = None,
    ) -> T:
        """
        Login with a password token. Used for logins after :meth:`.qrcode_login`.

        The created client instance will have its username and password
        attributes set to the credentials for the next login using
        :meth:`.token_login`.

        Args:
            pronote_url (str): URL of the server
            username (str)
            password (str): Password token received from the previous login
            uuid (str): Unique ID for your application. Must not change between logins.
            account_pin (Optional[str]): 2FA PIN to the account
            client_identifier (str): Identificator of this client provided by PRONOTE
            device_name (str): Identificator of this client provided by PRONOTE
        """
        return cls(
            pronote_url,
            username,
            password,
            mode="token",
            uuid=uuid,
            account_pin=account_pin,
            client_identifier=client_identifier,
            device_name=device_name,
        )

    def _login(self) -> bool:
        """Logs in the user.

        Returns:
            bool: True if logged in, False if not
        """

        if self.ent:
            username = self.attributes["e"]
            password = self.attributes["f"]
        else:
            username = self.username
            password = self.password

        # identification phase
        ident_json = {
            "genreConnexion": 0,
            "genreEspace": int(self.attributes["a"]),
            "identifiant": username,
            "pourENT": True if self.ent else False,
            "enConnexionAuto": False,
            "demandeConnexionAuto": False,
            "demandeConnexionAppliMobile": self.login_mode == "qr_code",
            "demandeConnexionAppliMobileJeton": self.login_mode == "qr_code",
            "enConnexionAppliMobile": self.login_mode == "token",
            "uuidAppliMobile": (
                self.uuid if self.login_mode in ("qr_code", "token") else ""
            ),
            "loginTokenSAV": "",
        }
        idr = self.post("Identification", data=ident_json)
        log.debug("indentification")

        # creating the authentification data
        log.debug(str(idr))
        challenge = idr["dataSec"]["data"]["challenge"]
        e = _Encryption()
        e.aes_set_iv(self.communication.encryption.aes_iv)

        # key gen
        if self.ent:
            motdepasse = SHA256.new(str(password).encode()).hexdigest().upper()
            e.aes_set_key(motdepasse.encode())
        else:
            if idr["dataSec"]["data"]["modeCompLog"]:
                username = username.lower()
            if idr["dataSec"]["data"]["modeCompMdp"]:
                password = password.lower()
            alea = idr["dataSec"]["data"].get("alea", "")
            motdepasse = SHA256.new((alea + password).encode()).hexdigest().upper()
            e.aes_set_key((username + motdepasse).encode())

        # challenge
        try:
            dec = e.aes_decrypt(bytes.fromhex(challenge))
            dec_no_alea = _enleverAlea(dec.decode())
            ch = e.aes_encrypt(dec_no_alea.encode()).hex()
        except CryptoError as ex:
            if self.login_mode == "qr_code":
                ex.args += (
                    "exception happened during login -> probably the qr code has expired (qr code is valid during 10 minutes)",
                )
            else:
                ex.args += (
                    "exception happened during login -> probably bad username/password",
                )
            raise

        # send
        auth_json = {
            "connexion": 0,
            "challenge": ch,
            "espace": int(self.attributes["a"]),
        }
        auth_response = self.post("Authentification", data=auth_json)
        if "cle" in auth_response["dataSec"]["data"]:
            self.communication.after_auth(auth_response, e.aes_key)
            self.encryption.aes_key = e.aes_key

            actionsDoubleAuth = auth_response["dataSec"]["data"].get(
                "actionsDoubleAuth"
            )
            if actionsDoubleAuth:
                actions = json.loads(actionsDoubleAuth["V"])

                doRegisterDevice = 5 in actions or 3 in actions
                doVerifyPin = 3 in actions

                self._do_2fa(
                    doVerifyPin,
                    doRegisterDevice,
                    self.account_pin,
                    self.device_name,
                )

            log.info(f"successfully logged in as {self.username}")

            last_conn = auth_response["dataSec"]["data"].get("derniereConnexion")
            self.last_connection = last_conn["V"] if last_conn else None

            if self.login_mode in ("qr_code", "token") and auth_response["dataSec"][
                "data"
            ].get("jetonConnexionAppliMobile"):
                self.password = auth_response["dataSec"]["data"][
                    "jetonConnexionAppliMobile"
                ]

            # getting listeOnglets separately because of pronote API change
            self.parametres_utilisateur = self.post("ParametresUtilisateur")
            self.info = self.parametres_utilisateur["dataSec"]["data"]["ressource"]
            self.communication.authorized_onglets = _prepare_onglets(
                self.parametres_utilisateur["dataSec"]["data"]["listeOnglets"]
            )
            log.info("got onglets data.")
            return True
        else:
            log.info("login failed")
            return False

    def _do_2fa(
        self,
        doVerifyPin: bool = False,
        doRegisterDevice: bool = False,
        pin: Optional[str] = None,
        identifier: Optional[str] = None,
    ) -> None:
        log.debug(
            "doing 2fa doPin=%s, doRegister=%s, pin=%s (redacted), identifier=%s",
            doVerifyPin,
            doRegisterDevice,
            bool(pin),
            identifier,
        )

        encryptedPin = None

        if doVerifyPin:
            log.debug("verifying pin")

            if pin is None:
                raise MFAError("PIN is required for this account")

            encryptedPin = self.communication.encryption.aes_encrypt(pin.encode()).hex()

            resp = self.post(
                "SecurisationCompteDoubleAuth",
                data={
                    "action": 0,
                    "codePin": encryptedPin,
                },
            )

            if not resp["dataSec"]["data"].get("result", False):
                raise MFAError("Invalid PIN")

        if doRegisterDevice:
            log.debug("registering device")

            if identifier is None:
                raise MFAError("A device identifier is required for this account")

            data = {
                "action": 3,
                "avecIdentification": True,
                "strIdentification": identifier,
            }
            if encryptedPin:
                data["codePin"] = encryptedPin

            self.post("SecurisationCompteDoubleAuth", data=data)

    def export_credentials(self) -> dict:
        return {
            "pronote_url": self.pronote_url,
            "username": self.username,
            "password": self.password,
            "client_identifier": self.client_identifier,
            "uuid": self.uuid,
        }

    def get_week(self, date: Union[datetime.date, datetime.datetime]) -> int:
        if isinstance(date, datetime.datetime):
            return 1 + int((date.date() - self.start_day).days / 7)
        return 1 + int((date - self.start_day).days / 7)

    def keep_alive(self) -> _KeepAlive:
        """
        Returns a context manager to keep the connection alive. When inside the context manager,
        it sends a "Navigation" request to the server after 5 minutes of inactivity from another thread.
        """
        return _KeepAlive(self)

    def refresh(self) -> None:
        """
        Now this is the true jank part of this program. It refreshes the connection if something went wrong.
        This is the classical procedure if something is broken.
        """
        logging.debug("Reinitialisation")
        self.communication.session.close()

        if self.ent:
            cookies = self.ent(
                self.username, self.password, pronote_url=self.pronote_url
            )
        else:
            cookies = None

        self.communication = _Communication(self.pronote_url, cookies)
        self.attributes, self.func_options = self.communication.initialise(
            self.client_identifier
        )

        # set up encryption

        self.encryption = _Encryption()
        self.encryption.aes_iv = self.communication.encryption.aes_iv
        self._login()
        self.week = self.get_week(datetime.date.today())
        self._expired = True

    def session_check(self) -> bool:
        """Checks if the session has expired and refreshes it if it had (returns bool signifying if it was expired)"""
        self.post("Navigation", 7, {"onglet": 7, "ongletPrec": 7})
        if self._expired:
            self._expired = False
            return True
        return False

    def post(
        self,
        function_name: str,
        onglet: Optional[int] = None,
        data: Optional[dict] = None,
    ) -> dict:
        """Preforms a raw post to the PRONOTE server. Adds signature, then passes it to _Communication.post

        Args:
            function_name (str)
            onglet (int)
            data (dict)
        Returns:
            dict: Raw JSON
        """
        post_data = {}
        if onglet:
            post_data["Signature"] = {"onglet": onglet}
        if data:
            post_data["data"] = data

        try:
            return self.communication.post(function_name, post_data)
        except PronoteAPIError as e:
            if isinstance(e, ExpiredObject):
                raise e

            log.info(
                f"Have you tried turning it off and on again? ERROR: {e.pronote_error_code} | {e.pronote_error_msg}"
            )

            # prevent refresh recursion
            if self._refreshing:
                raise e
            else:
                self._refreshing = True
                self.refresh()
                self._refreshing = False

            return self.communication.post(function_name, post_data)

    def request_qr_code_data(self, pin: str) -> dict:
        """
        Requests data for a new login QR code. This data can be then used with :meth:`.qrcode_login`.

        Args:
            pin (str): Four digit pin to use for the QR code
        """
        req = self.post("JetonAppliMobile", 7, {"code": pin})
        return {
            # ugly way to add the mobile prefix to the url
            "url": re.sub(
                r"/(?:mobile.){,1}(\w+).html$", r"/mobile.\1.html", self.pronote_url
            ),
            **req["dataSec"]["data"],
        }
