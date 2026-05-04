import urllib.request
import urllib.error


class LoranStorageInterface:
    def __init__(self, url_base, app_name, url_after, password, limit, after):
        self.url_base = url_base
        self.app_name = app_name
        self.url_after = url_after
        self.password = password
        self.limit = limit
        self.after = after

    def _request_url(self):
        return (
            f"{self.url_base}{self.app_name}{self.url_after}"
            f"limit={self.limit}&after={self.after}"
        )

    def get_raw_stream(self):
        request_string = self._request_url()
        print("request_string", request_string)
        req = urllib.request.Request(
            request_string,
            method="GET",
            headers={
                "Authorization": f"Bearer {self.password}",
                "Accept": "text/event-stream",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            return body, True
        except urllib.error.URLError as exc:
            print("request error:", exc)
            return "", False

    def get_data(self):
        raw_text_stream, ok = self.get_raw_stream()
        if not ok:
            print("bad")
        print("raw_text_stream", raw_text_stream)
        return raw_text_stream


if __name__ == "__main__":
    url_base = "https://nam1.cloud.thethings.network/api/v3/as/applications/"
    app_name = "seeedec"
    url_after = "/packages/storage/uplink_message?"
    limit = "200"
    after = "2020-08-20T00:00:00Z"
    password = (
        "NNSXS.5N2DRLTP3QD4SNMBXNWXZ6V3SMPEGXSW6JOT25I."
        "7VUBLSUKWWEK4KAQUY3SP66Z6YHLQQVMRIKTWL2I7GH4GNRHETIA"
    )

    client = LoranStorageInterface(
        url_base=url_base,
        app_name=app_name,
        url_after=url_after,
        password=password,
        limit=limit,
        after=after,
    )
    client.get_data()
