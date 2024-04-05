import scrypted_sdk
from scrypted_sdk import ScryptedDeviceBase, DeviceProvider, DeviceCreator, DeviceCreatorSettings, MediaObject, Notifier, NotifierOptions, Settings, Setting, ScryptedInterface, ScryptedDeviceType

import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from smtplib import SMTP, SMTP_SSL, SMTPException
from typing import Dict
import uuid


class SMTPNotifier(ScryptedDeviceBase, Settings, Notifier):
    client: SMTP | SMTP_SSL

    def __init__(self, nativeId: str) -> None:
        super().__init__(nativeId)
        self.client = None

        asyncio.get_event_loop().call_soon(self.initialize)

    def print(self, *args, **kwargs) -> None:
        super().print(f"[{self.name}]", *args, **kwargs)

    @property
    def server(self) -> str:
        return self.storage.getItem('server')

    @property
    def port(self) -> int:
        port = self.storage.getItem('port')
        if port is None:
            return 465
        return int(port)

    @property
    def ssl_enabled(self) -> bool:
        enabled = self.storage.getItem('ssl_enabled')
        if enabled is None:
            return True
        return bool(enabled)

    @property
    def username(self) -> str:
        return self.storage.getItem('username')

    @property
    def password(self) -> str:
        return self.storage.getItem('password')

    @property
    def from_email(self) -> str:
        return self.storage.getItem('from_email')

    @property
    def to_email(self) -> str:
        return self.storage.getItem('to_email')

    def initialize(self) -> None:
        if any([
            not self.server,
            not self.port,
            not self.username,
            not self.password,
            not self.from_email,
            not self.to_email
        ]):
            return

        try:
            if self.ssl_enabled:
                self.client = SMTP_SSL(self.server, self.port, timeout=5)
            else:
                self.client = SMTP(self.server, self.port, timeout=5)
                try:
                    self.client.starttls()
                except SMTPException as e:
                    self.print('SMTP server does not support STARTTLS. SSL not enabled.')

            self.client.login(self.username, self.password)
        except Exception as e:
            self.print(f'Error connecting to SMTP server: {e}')
            self.client = None
        else:
            self.print('SMTP client initialized.')

    async def getSettings(self) -> list[Setting]:
        return [
            {
                'title': 'SMTP Server',
                'key': 'server',
                'value': self.server,
                'type': 'string'
            },
            {
                'title': 'SMTP Port',
                'key': 'port',
                'value': self.port,
                'type': 'number'
            },
            {
                'title': 'SMTP SSL',
                'key': 'ssl_enabled',
                'value': self.ssl_enabled,
                'description': 'Require SSL when connecting to the SMTP server. If unset, will attempt to use STARTTLS.',
                'type': 'boolean'
            },
            {
                'title': 'SMTP Username',
                'key': 'username',
                'value': self.username,
                'type': 'string'
            },
            {
                'title': 'SMTP Password',
                'key': 'password',
                'value': self.password,
                'type': 'password'
            },
            {
                'title': 'From Email',
                'key': 'from_email',
                'value': self.from_email,
                'type': 'string'
            },
            {
                'title': 'To Email',
                'key': 'to_email',
                'value': self.to_email,
                'type': 'string'
            }
        ]

    async def putSetting(self, key: str, value: str) -> None:
        if key == 'port':
            try:
                value = int(value)
            except:
                msg = 'Port must be a number.'
                self.print(msg)
                raise Exception(msg)

            if value < 0 or value > 65535:
                msg = 'Port must be between 0 and 65535.'
                self.print(msg)
                raise Exception(msg)

        if key == 'ssl_enabled':
            value = value == "true" or value == True

        self.storage.setItem(key, value)
        await self.onDeviceEvent(ScryptedInterface.Settings.value, None)

        self.initialize()

    async def sendNotification(self, title: str, options: NotifierOptions = None, media: str | MediaObject = None, icon: str | scrypted_sdk.MediaObject = None) -> None:
        self.initialize()
        if not self.client:
            msg = 'SMTP client not initialized.'
            self.print(msg)
            raise Exception(msg)

        self.print(f'Sending email to {self.to_email}...')

        body = options.get('body', '') if options else ''

        message = MIMEMultipart()
        message['From'] = self.from_email
        message['To'] = self.to_email
        message['Subject'] = title
        message.attach(MIMEText(body, 'plain'))

        if media:
            if isinstance(media, str):
                media = await scrypted_sdk.mediaManager.createMediaObjectFromUrl(media)
            data = await scrypted_sdk.mediaManager.convertMediaObjectToBuffer(media, 'image/png')
            image = MIMEImage(data)
            image.add_header('Content-Disposition', "attachment; filename=image.png")
            message.attach(image)

        try:
            self.client.send_message(message)
            self.print('Email sent successfully.')
        except SMTPException as e:
            self.print(f'Error sending email: {e}')


class SMTPNotifierProvider(ScryptedDeviceBase, DeviceProvider, DeviceCreator):
    notifiers: Dict[str, SMTPNotifier]

    def __init__(self, nativeId: str = None) -> None:
        super().__init__(nativeId=nativeId)
        self.notifiers = {}

    def print(self, *args, **kwargs) -> None:
        """Overrides the print() from ScryptedDeviceBase to avoid double-printing in the main plugin console."""
        print(*args, **kwargs)

    async def getDevice(self, nativeId: str) -> SMTPNotifier:
        if nativeId not in self.notifiers:
            self.notifiers[nativeId] = SMTPNotifier(nativeId)
        return self.notifiers[nativeId]

    async def releaseDevice(self, id: str, nativeId: str) -> None:
        if nativeId in self.notifiers:
            del self.notifiers[nativeId]

    async def createDevice(self, settings: DeviceCreatorSettings) -> str:
        nativeId = str(uuid.uuid4())
        name = settings.get("name", "New SMTP Notifier")
        await scrypted_sdk.deviceManager.onDeviceDiscovered({
            'nativeId': nativeId,
            'name': name,
            'interfaces': [
                ScryptedInterface.Notifier.value,
                ScryptedInterface.Settings.value
            ],
            'type': ScryptedDeviceType.Notifier.value,
        })
        await self.getDevice(nativeId)
        return nativeId

    async def getCreateDeviceSettings(self) -> list[Setting]:
        return [
            {
                'title': 'Name',
                'key': 'name'
            }
        ]


def create_scrypted_plugin():
    return SMTPNotifierProvider()