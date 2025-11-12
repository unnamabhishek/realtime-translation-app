#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import argparse
import os
from typing import Tuple

import aiohttp
from pipecat.transports.daily.utils import (
    DailyMeetingTokenParams,
    DailyMeetingTokenProperties,
    DailyRESTHelper,
)


async def configure(aiohttp_session: aiohttp.ClientSession) -> Tuple[str, str]:
    """Configure Daily room connection and return room URL and token."""
    parser = argparse.ArgumentParser(description="Daily AI SDK Bot Sample")
    parser.add_argument(
        "-u", "--url", type=str, required=False, help="URL of the Daily room to join"
    )
    parser.add_argument(
        "-k",
        "--apikey",
        type=str,
        required=False,
        help="Daily API Key (needed to create an owner token for the room)",
    )
    parser.add_argument(
        "-t",
        "--token",
        type=str,
        required=False,
        help="Daily meeting token (if not provided, will be generated)",
    )

    args, unknown = parser.parse_known_args()

    url = args.url or os.getenv("DAILY_SAMPLE_ROOM_URL")
    key = args.apikey or os.getenv("DAILY_API_KEY")
    token = args.token or os.getenv("DAILY_MEETING_TOKEN")

    if not url:
        raise RuntimeError(
            "No Daily room specified. Use the -u/--url option from the command line, or set DAILY_SAMPLE_ROOM_URL in your environment to specify a Daily room URL."
        )

    # If token is provided, use it directly
    if token:
        return (url, token)

    # Otherwise, generate a token
    if not key:
        raise RuntimeError(
            "No Daily API key specified. Use the -k/--apikey option from the command line, or set DAILY_API_KEY in your environment to specify a Daily API key, available from https://dashboard.daily.co/developers."
        )

    daily_rest_helper = DailyRESTHelper(
        daily_api_key=key,
        daily_api_url=os.getenv("DAILY_API_URL", "https://api.daily.co/v1"),
        aiohttp_session=aiohttp_session,
    )

    # Create a meeting token for the given room with an expiration 1 hour in
    # the future.
    expiry_time: float = 60 * 60

    token = await daily_rest_helper.get_token(
        url,
        expiry_time,
        params=DailyMeetingTokenParams(
            properties=DailyMeetingTokenProperties(start_video_off=True)
        ),
    )

    return (url, token)
