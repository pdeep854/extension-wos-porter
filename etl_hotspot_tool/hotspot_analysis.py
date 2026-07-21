# Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause-Clear

"""
WPA Hotspot Tool - Command-line version:
  Generate SymCache -> Run wpaexporter -> Analyze hotspots

Usage:
    python hotspot_tool_cli.py <modules_folder> <etl_file> --process <name> --module <name>
    python hotspot_tool_cli.py <modules_folder> <etl_file> --source-dir <path>  [--process <name>]
    python hotspot_tool_cli.py <modules_folder> <etl_file> --list-processes
    python hotspot_tool_cli.py <modules_folder> <etl_file> --process <name> --list-modules

  Source-code matching mode (--source-dir):
    Cross-references hotspot functions against source code, showing only
    functions that exist in the provided source tree, ranked by CPU weight.

  All prompts support 'exit'/'quit'/'q' to exit at any time.

Dependencies are auto-installed on first run (pandas via pip).
WPT tools are copied from network share to local cache to avoid DLL loading issues.
"""

import struct
import os
import subprocess
import sys
import shutil
import urllib.request
import re
import tempfile
import argparse
from collections import Counter
from pathlib import Path

# =============================================================================
# Dependency Bootstrap
# =============================================================================

REQUIRED_PACKAGES = ["pandas"]


def ensure_pip():
    try:
        import importlib
        importlib.import_module("pip")
    except ImportError:
        print("pip not found, bootstrapping via ensurepip...")
        try:
            import ensurepip
            ensurepip.bootstrap(upgrade=True)
        except Exception:
            print("ensurepip failed, downloading get-pip.py...")
            get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
            get_pip_path = os.path.join(tempfile.gettempdir(), "get-pip.py")
            urllib.request.urlretrieve(get_pip_url, get_pip_path)
            subprocess.check_call([sys.executable, get_pip_path])


def install_missing_packages():
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"Installing missing packages: {', '.join(missing)}")
        ensure_pip()
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing
        )
        print("Installation complete.")


install_missing_packages()

import pandas as pd

# =============================================================================
# WPT Tools - Local Cache
# =============================================================================

# WPT tools source. Prefer tools already on PATH or in the standard Windows Kits
# install; only fall back to a share when neither is present. Both the share and
# a direct local WPT folder are overridable via environment variables so the tool
# is not tied to any one corp network location:
#   WOS_WPT_DIR  — a local Windows Performance Toolkit folder to use directly.
#   WOS_WPT_PATH — a (possibly network) folder to copy WPT tools from into a cache.
DEFAULT_WPT_NETWORK_PATH = r"\\blrsweng1\winmblr_performance4\Niranjan\App_compat_scrum\Qgeine\30_6_2026\WindowsPerformanceToolkit"
WPT_NETWORK_PATH = os.environ.get("WOS_WPT_PATH", DEFAULT_WPT_NETWORK_PATH)
WPT_LOCAL_CACHE = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()),
                               "WPA_HotspotTool", "WindowsPerformanceToolkit")

STANDARD_WPT_DIRS = [
    r"C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit",
    r"C:\Program Files\Windows Kits\10\Windows Performance Toolkit",
]


def _dir_has_wpt(d):
    return bool(d) and os.path.isdir(d) and os.path.exists(os.path.join(d, "wpaexporter.exe"))


def ensure_wpt_tools_local():
    # 1) explicit local override
    env_dir = os.environ.get("WOS_WPT_DIR")
    if _dir_has_wpt(env_dir):
        return env_dir
    # 2) already cached
    marker = os.path.join(WPT_LOCAL_CACHE, ".copied")
    if os.path.exists(marker):
        return WPT_LOCAL_CACHE
    # 3) standard Windows Kits install
    for d in STANDARD_WPT_DIRS:
        if _dir_has_wpt(d):
            return d
    # 4) copy from the (possibly network) share into a local cache
    if not os.path.isdir(WPT_NETWORK_PATH):
        print(f"WARNING: WPT source not accessible: {WPT_NETWORK_PATH}")
        print("Set WOS_WPT_DIR to a local Windows Performance Toolkit folder, or")
        print("install the Windows ADK/WPT so wpaexporter.exe/wpr.exe are on PATH.")
        return WPT_NETWORK_PATH
    print(f"Copying WPT tools to local cache: {WPT_LOCAL_CACHE}")
    print("(This is a one-time operation...)")
    if os.path.exists(WPT_LOCAL_CACHE):
        shutil.rmtree(WPT_LOCAL_CACHE)
    shutil.copytree(WPT_NETWORK_PATH, WPT_LOCAL_CACHE)
    with open(marker, "w") as f:
        f.write("ok")
    print("WPT tools cached locally.")
    return WPT_LOCAL_CACHE


WPT_TOOLS_DIR = ensure_wpt_tools_local()

# =============================================================================
# Constants
# =============================================================================

SYMBOL_PATH = r"srv*C:\Symbols*https://msdl.microsoft.com/download/symbols"
SYMCACHE_DIR = r"C:\SymCache"

WPA_PROFILE_XML = r"""<?xml version="1.0" encoding="utf-8"?>
<WpaProfileContainer xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" Version="2" xmlns="http://tempuri.org/SerializableElement.xsd">
  <Content xsi:type="WpaProfile2">
    <Sessions>
      <Session Index="0">
        <FileReferences />
      </Session>
    </Sessions>
    <Views>
      <View Guid="0dd0f892-c905-4b5a-a5a3-96459e89171d" IsVisible="true" Title="Analysis">
        <Graphs>
          <Graph Guid="b855361e-7be0-4bc8-a754-3e8507715ca5" LayoutStyle="All" GraphHeight="125" IsMinimized="false" IsShown="true" IsExpanded="false" HelpText="{}{\rtf1\ansi\ansicpg1252\uc1\htmautsp\deff2{\fonttbl{\f0\fcharset0 Times New Roman;}{\f2\fcharset0 Segoe UI;}}{\colortbl\red0\green0\blue0;\red255\green255\blue255;}\loch\hich\dbch\pard\plain\ltrpar\itap0{\lang1033\fs18\f2\cf0 \cf0\ql{\f2 {\ltrch This graph shows CPU usage events logged at a regular sampling interval, usually about 1ms.  Each event logs the CPU, thread, address and optionally the call stack.}\li0\ri0\sa0\sb0\fi0\ql\par}">
            <Preset Name="Utilization by Process, Stack" BarGraphIntervalCount="50" IsThreadActivityTable="false" GraphColumnCount="26" KeyColumnCount="8" LeftFrozenColumnCount="0" RightFrozenColumnCount="22" InitialFilterQuery="[DPC/ISR]:=&quot;DPC&quot; OR [DPC/ISR]:=&quot;ISR&quot;" InitialFilterShouldKeep="false" InitialSelectionQuery="([Series Name]:=&quot;Process&quot; AND NOT ([Process]:=&quot;Idle (0)&quot;))" GraphFilterColumnGuid="01a82c2c-5048-4c9d-ac37-eaf6556f6af5" GraphFilterTopValue="0" GraphFilterThresholdValue="0">
              <MetadataEntries>
                <MetadataEntry Guid="05100ece-df05-40c7-aad6-ffff99b60491" Name="Thread ID" ColumnMetadata="EndThreadId" />
                <MetadataEntry Guid="0bbf4299-0176-445e-b1d9-991df475d631" Name="TimeStamp" ColumnMetadata="EndTime" />
                <MetadataEntry Guid="e0c6cb9e-04c2-4bb5-ba5f-4ed765f4ecaa" Name="Weight" ColumnMetadata="Duration" />
                <MetadataEntry Guid="55d56ebb-77af-4af5-a056-6122751ea093" Name="CPU" ColumnMetadata="ResourceId" />
              </MetadataEntries>
              <HighlightEntries />
              <Columns>
                <Column Guid="00875e0c-482f-418d-ab40-decf05030541" Name="Display Name" SortPriority="1" Width="200" IsVisible="false">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="842af11e-661d-477e-b7b6-556ed8181177" Name="Stack Tag" SortPriority="2" Width="200" IsVisible="false">
                  <StackOptionsParameter Mode="StackTag" StackFrameInvert="false" />
                  <ColorQueryEntries />
                </Column>
                <Column Guid="842af11e-661d-477e-b7b6-556ed8181177" Name="Stack (Frame Tags)" SortPriority="3" Width="200" IsVisible="false">
                  <StackOptionsParameter Mode="FrameTags" StackFrameInvert="false" />
                  <ColorQueryEntries />
                </Column>
                <Column Guid="842af11e-661d-477e-b7b6-556ed8181177" Name="Stack" SortPriority="4" Width="372" IsVisible="false">
                  <StackOptionsParameter StackFrameInvert="false" />
                  <ColorQueryEntries />
                </Column>
                <Column Guid="d0028ea0-aa66-452a-882a-616fd8b9fdce" Name="DPC/ISR" SortPriority="5" Width="184" IsVisible="false">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="9aa2e00d-db0a-4207-a0bd-964aa492356e" Name="Address" SortPriority="6" TextAlignment="Right" Width="140" CellFormat="x" IsVisible="false">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="05100ece-df05-40c7-aad6-ffff99b60491" Name="Thread ID" SortPriority="7" TextAlignment="Right" Width="80" IsVisible="false">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="cb796d44-2927-5ac1-d231-4b71904c18f5" Name="Thread Name" SortPriority="8" Width="80" IsVisible="false">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="82ddfdff-ee93-5f35-08ac-4705069618dc" Name="Thread Activity Tag" SortPriority="9" Width="80" IsVisible="false">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="2818954f-2d30-5569-4510-dade0a5a605c" Name="Annotation" SortPriority="10" Width="80" IsVisible="false">
                  <AnnotationsOptionsParameter>
                    <AnnotationQueryEntries />
                  </AnnotationsOptionsParameter>
                  <ColorQueryEntries />
                </Column>
                <Column Guid="32acf445-36b3-456e-a54e-19bcad276a4f" Name="WorkOnBehalf Thread ID" SortPriority="11" TextAlignment="Right" Width="80" IsVisible="false">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="303f4b83-026a-4142-979a-247296c5f4cb" Name="WorkOnBehalf Process Name" SortPriority="12" TextAlignment="Right" Width="180" IsVisible="false">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="56e0aeb4-5ed0-44a6-a60b-9db4e918e5a1" Name="WorkOnBehalf Process" SortPriority="13" TextAlignment="Right" Width="200" IsVisible="false">
                  <ProcessOptionsParameter />
                  <ColorQueryEntries />
                </Column>
                <Column Guid="9c1ceec3-ef4a-4865-b678-d774881187b9" Name="Process Name" SortPriority="14" Width="180" IsVisible="false">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="55d56ebb-77af-4af5-a056-6122751ea093" Name="CPU" SortPriority="15" TextAlignment="Right" Width="40" IsVisible="false">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="5b77e48f-6d24-4f29-8972-69c30e32f87d" Name="Process" SortPriority="16" Width="321" IsVisible="true">
                  <ProcessOptionsParameter SeparateDpcIsr="false" />
                  <ColorQueryEntries />
                </Column>
                <Column Guid="ccdb05c1-04a9-4289-aaa6-a376d1d66012" Name="Module" SortOrder="Ascending" SortPriority="0" Width="124" IsVisible="true">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="7ad93780-708c-471c-9e3f-5a497cbefdd7" Name="Function" SortPriority="18" Width="293" IsVisible="true">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="01a82c2c-5048-4c9d-ac37-eaf6556f6af5" Name="Count" AggregationMode="Sum" SortPriority="19" TextAlignment="Right" Width="60" IsVisible="true">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="63cfb4e2-a24c-4e9d-80f2-393f03794d60" Name="Weight (in view)" AggregationMode="Sum" SortPriority="20" TextAlignment="Right" Width="100" CellFormat="mN" IsVisible="true">
                  <DurationInViewOptionsParameter TimeStampColumnGuid="0bbf4299-0176-445e-b1d9-991df475d631" TimeStampType="Start" InViewEnabled="false" />
                  <ColorQueryEntries />
                </Column>
                <Column Guid="0bbf4299-0176-445e-b1d9-991df475d631" Name="TimeStamp" SortPriority="21" TextAlignment="Right" Width="100" IsVisible="true">
                  <DateTimeTimestampOptionsParameter DateTimeEnabled="false" />
                  <ColorQueryEntries />
                </Column>
                <Column Guid="ab54241e-ce5d-4ef7-a28c-bbcb5b8d39d4" Name="Rank" SortPriority="22" TextAlignment="Right" Width="80" IsVisible="false">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="5a1e1ba4-6a14-43e5-96eb-3b462be470fe" Name="Priority" SortPriority="23" TextAlignment="Right" Width="80" IsVisible="false">
                  <ColorQueryEntries />
                </Column>
                <Column Guid="f5ebf01b-f7cb-4afb-877d-c36edb2a62b6" Name="% Weight" AggregationMode="Sum" SortPriority="24" TextAlignment="Right" Width="80" CellFormat="N2" IsVisible="true">
                  <ColorQueryEntries />
                </Column>
              </Columns>
            </Preset>
          </Graph>
        </Graphs>
        <SessionIndices>
          <SessionIndex>0</SessionIndex>
        </SessionIndices>
      </View>
    </Views>
    <ModifiedGraphs>
      <GraphSchema Guid="b855361e-7be0-4bc8-a754-3e8507715ca5" HelpText="{}{\rtf1\ansi\ansicpg1252\uc1\htmautsp\deff2{\fonttbl{\f0\fcharset0 Times New Roman;}{\f2\fcharset0 Segoe UI;}}{\colortbl\red0\green0\blue0;\red255\green255\blue255;}\loch\hich\dbch\pard\plain\ltrpar\itap0{\lang1033\fs18\f2\cf0 \cf0\ql{\f2 {\ltrch This graph shows CPU usage events logged at a regular sampling interval, usually about 1ms.  Each event logs the CPU, thread, address and optionally the call stack.}\li0\ri0\sa0\sb0\fi0\ql\par}">
        <ModifiedPresets />
        <PersistedPresets>
          <Preset Name="Utilization by Process, Stack" BarGraphIntervalCount="50" IsThreadActivityTable="false" GraphColumnCount="26" KeyColumnCount="12" LeftFrozenColumnCount="0" RightFrozenColumnCount="22" InitialFilterQuery="[DPC/ISR]:=&quot;DPC&quot; OR [DPC/ISR]:=&quot;ISR&quot;" InitialFilterShouldKeep="false" InitialSelectionQuery="([Series Name]:=&quot;Process&quot; AND NOT ([Process]:=&quot;Idle (0)&quot;))" GraphFilterColumnGuid="01a82c2c-5048-4c9d-ac37-eaf6556f6af5" GraphFilterTopValue="0" GraphFilterThresholdValue="0">
            <MetadataEntries>
              <MetadataEntry Guid="05100ece-df05-40c7-aad6-ffff99b60491" Name="Thread ID" ColumnMetadata="EndThreadId" />
              <MetadataEntry Guid="0bbf4299-0176-445e-b1d9-991df475d631" Name="TimeStamp" ColumnMetadata="EndTime" />
              <MetadataEntry Guid="e0c6cb9e-04c2-4bb5-ba5f-4ed765f4ecaa" Name="Weight" ColumnMetadata="Duration" />
              <MetadataEntry Guid="55d56ebb-77af-4af5-a056-6122751ea093" Name="CPU" ColumnMetadata="ResourceId" />
            </MetadataEntries>
            <HighlightEntries />
            <Columns>
              <Column Guid="9c1ceec3-ef4a-4865-b678-d774881187b9" Name="Process Name" SortPriority="1" Width="180" IsVisible="false">
                <ColorQueryEntries />
              </Column>
              <Column Guid="00875e0c-482f-418d-ab40-decf05030541" Name="Display Name" SortPriority="2" Width="200" IsVisible="false">
                <ColorQueryEntries />
              </Column>
              <Column Guid="5b77e48f-6d24-4f29-8972-69c30e32f87d" Name="Process" SortPriority="3" Width="200" IsVisible="true">
                <ProcessOptionsParameter SeparateDpcIsr="false" />
                <ColorQueryEntries />
              </Column>
              <Column Guid="842af11e-661d-477e-b7b6-556ed8181177" Name="Stack Tag" SortPriority="4" Width="200" IsVisible="false">
                <StackOptionsParameter Mode="StackTag" StackFrameInvert="false" />
                <ColorQueryEntries />
              </Column>
              <Column Guid="842af11e-661d-477e-b7b6-556ed8181177" Name="Stack (Frame Tags)" SortPriority="5" Width="200" IsVisible="false">
                <StackOptionsParameter Mode="FrameTags" StackFrameInvert="false" />
                <ColorQueryEntries />
              </Column>
              <Column Guid="842af11e-661d-477e-b7b6-556ed8181177" Name="Stack" SortPriority="6" Width="332" IsVisible="false">
                <StackOptionsParameter StackFrameInvert="false" />
                <ColorQueryEntries />
              </Column>
              <Column Guid="ccdb05c1-04a9-4289-aaa6-a376d1d66012" Name="Module" SortPriority="7" Width="124" IsVisible="true">
                <ColorQueryEntries />
              </Column>
              <Column Guid="7ad93780-708c-471c-9e3f-5a497cbefdd7" Name="Function" SortPriority="8" Width="184" IsVisible="true">
                <ColorQueryEntries />
              </Column>
              <Column Guid="d0028ea0-aa66-452a-882a-616fd8b9fdce" Name="DPC/ISR" SortPriority="9" Width="184" IsVisible="false">
                <ColorQueryEntries />
              </Column>
              <Column Guid="9aa2e00d-db0a-4207-a0bd-964aa492356e" Name="Address" SortPriority="10" TextAlignment="Right" Width="140" CellFormat="x" IsVisible="false">
                <ColorQueryEntries />
              </Column>
              <Column Guid="05100ece-df05-40c7-aad6-ffff99b60491" Name="Thread ID" SortPriority="11" TextAlignment="Right" Width="80" IsVisible="false">
                <ColorQueryEntries />
              </Column>
              <Column Guid="cb796d44-2927-5ac1-d231-4b71904c18f5" Name="Thread Name" SortPriority="12" Width="80" IsVisible="false">
                <ColorQueryEntries />
              </Column>
              <Column Guid="82ddfdff-ee93-5f35-08ac-4705069618dc" Name="Thread Activity Tag" SortPriority="13" Width="80" IsVisible="false">
                <ColorQueryEntries />
              </Column>
              <Column Guid="2818954f-2d30-5569-4510-dade0a5a605c" Name="Annotation" SortPriority="14" Width="80" IsVisible="false">
                <AnnotationsOptionsParameter>
                  <AnnotationQueryEntries />
                </AnnotationsOptionsParameter>
                <ColorQueryEntries />
              </Column>
              <Column Guid="32acf445-36b3-456e-a54e-19bcad276a4f" Name="WorkOnBehalf Thread ID" SortPriority="15" TextAlignment="Right" Width="80" IsVisible="false">
                <ColorQueryEntries />
              </Column>
              <Column Guid="303f4b83-026a-4142-979a-247296c5f4cb" Name="WorkOnBehalf Process Name" SortPriority="16" TextAlignment="Right" Width="180" IsVisible="false">
                <ColorQueryEntries />
              </Column>
              <Column Guid="56e0aeb4-5ed0-44a6-a60b-9db4e918e5a1" Name="WorkOnBehalf Process" SortPriority="17" TextAlignment="Right" Width="200" IsVisible="false">
                <ProcessOptionsParameter />
                <ColorQueryEntries />
              </Column>
              <Column Guid="55d56ebb-77af-4af5-a056-6122751ea093" Name="CPU" SortPriority="18" TextAlignment="Right" Width="40" IsVisible="false">
                <ColorQueryEntries />
              </Column>
              <Column Guid="01a82c2c-5048-4c9d-ac37-eaf6556f6af5" Name="Count" AggregationMode="Sum" SortPriority="19" TextAlignment="Right" Width="60" IsVisible="true">
                <ColorQueryEntries />
              </Column>
              <Column Guid="63cfb4e2-a24c-4e9d-80f2-393f03794d60" Name="Weight (in view)" AggregationMode="Sum" SortOrder="Descending" SortPriority="0" TextAlignment="Right" Width="100" CellFormat="mN" IsVisible="true">
                <DurationInViewOptionsParameter TimeStampColumnGuid="0bbf4299-0176-445e-b1d9-991df475d631" TimeStampType="Start" InViewEnabled="false" />
                <ColorQueryEntries />
              </Column>
              <Column Guid="0bbf4299-0176-445e-b1d9-991df475d631" Name="TimeStamp" SortPriority="20" TextAlignment="Right" Width="100" IsVisible="true">
                <DateTimeTimestampOptionsParameter DateTimeEnabled="false" />
                <ColorQueryEntries />
              </Column>
              <Column Guid="ab54241e-ce5d-4ef7-a28c-bbcb5b8d39d4" Name="Rank" SortPriority="21" TextAlignment="Right" Width="80" IsVisible="false">
                <ColorQueryEntries />
              </Column>
              <Column Guid="5a1e1ba4-6a14-43e5-96eb-3b462be470fe" Name="Priority" SortPriority="22" TextAlignment="Right" Width="80" IsVisible="false">
                <ColorQueryEntries />
              </Column>
              <Column Guid="f5ebf01b-f7cb-4afb-877d-c36edb2a62b6" Name="% Weight" AggregationMode="Sum" SortPriority="23" TextAlignment="Right" Width="80" CellFormat="N2" IsVisible="true">
                <ColorQueryEntries />
              </Column>
            </Columns>
          </Preset>
        </PersistedPresets>
      </GraphSchema>
    </ModifiedGraphs>
  </Content>
</WpaProfileContainer>
"""

# =============================================================================
# PE / PDB / SymCache Core Logic
# =============================================================================

IMAGE_DOS_SIGNATURE = 0x5A4D
IMAGE_NT_SIGNATURE = 0x4550
IMAGE_DIRECTORY_ENTRY_DEBUG = 6
IMAGE_DEBUG_TYPE_CODEVIEW = 2
CV_SIGNATURE_RSDS = b"RSDS"


def read_debug_info_from_pe(pe_path):
    with open(pe_path, "rb") as f:
        dos_sig = struct.unpack("<H", f.read(2))[0]
        if dos_sig != IMAGE_DOS_SIGNATURE:
            raise ValueError(f"Not a valid PE file: {pe_path}")

        f.seek(0x3C)
        pe_offset = struct.unpack("<I", f.read(4))[0]

        f.seek(pe_offset)
        pe_sig = struct.unpack("<I", f.read(4))[0]
        if pe_sig != IMAGE_NT_SIGNATURE:
            raise ValueError(f"Invalid PE signature in: {pe_path}")

        machine = struct.unpack("<H", f.read(2))[0]
        num_sections = struct.unpack("<H", f.read(2))[0]
        f.read(12)
        optional_header_size = struct.unpack("<H", f.read(2))[0]
        f.read(2)

        optional_header_start = f.tell()
        magic = struct.unpack("<H", f.read(2))[0]

        if magic == 0x20B:
            f.seek(optional_header_start + 108)
            num_data_dirs = struct.unpack("<I", f.read(4))[0]
            f.seek(optional_header_start + 112 + IMAGE_DIRECTORY_ENTRY_DEBUG * 8)
        elif magic == 0x10B:
            f.seek(optional_header_start + 92)
            num_data_dirs = struct.unpack("<I", f.read(4))[0]
            f.seek(optional_header_start + 96 + IMAGE_DIRECTORY_ENTRY_DEBUG * 8)
        else:
            raise ValueError(f"Unknown PE optional header magic: {hex(magic)}")

        debug_dir_rva = struct.unpack("<I", f.read(4))[0]
        debug_dir_size = struct.unpack("<I", f.read(4))[0]

        if debug_dir_rva == 0:
            raise ValueError("No debug directory found in PE file")

        f.seek(optional_header_start + optional_header_size)
        sections = []
        for _ in range(num_sections):
            sec_data = f.read(40)
            virtual_size = struct.unpack("<I", sec_data[8:12])[0]
            virtual_addr = struct.unpack("<I", sec_data[12:16])[0]
            raw_offset = struct.unpack("<I", sec_data[20:24])[0]
            sections.append({
                "virtual_addr": virtual_addr,
                "virtual_size": virtual_size,
                "raw_offset": raw_offset,
            })

        def rva_to_offset(rva):
            for sec in sections:
                if sec["virtual_addr"] <= rva < sec["virtual_addr"] + sec["virtual_size"]:
                    return rva - sec["virtual_addr"] + sec["raw_offset"]
            return rva

        debug_offset = rva_to_offset(debug_dir_rva)
        num_entries = debug_dir_size // 28

        for i in range(num_entries):
            f.seek(debug_offset + i * 28)
            entry = f.read(28)
            debug_type = struct.unpack("<I", entry[12:16])[0]
            pointer_to_raw_data = struct.unpack("<I", entry[24:28])[0]

            if debug_type == IMAGE_DEBUG_TYPE_CODEVIEW:
                f.seek(pointer_to_raw_data)
                cv_sig = f.read(4)

                if cv_sig == CV_SIGNATURE_RSDS:
                    data1 = struct.unpack("<I", f.read(4))[0]
                    data2 = struct.unpack("<H", f.read(2))[0]
                    data3 = struct.unpack("<H", f.read(2))[0]
                    data4 = f.read(8)
                    age = struct.unpack("<I", f.read(4))[0]

                    pdb_name_bytes = b""
                    while True:
                        ch = f.read(1)
                        if ch == b"\x00" or ch == b"":
                            break
                        pdb_name_bytes += ch
                    pdb_name = os.path.basename(pdb_name_bytes.decode("utf-8", errors="replace"))

                    guid_str = f"{data1:08X}{data2:04X}{data3:04X}" + data4.hex().upper()
                    return pdb_name, guid_str, age

    raise ValueError("No RSDS CodeView debug info found in PE file")


def find_pdb_in_sympath(pdb_name, guid_str, age, sympath):
    key = f"{guid_str}{age:X}"
    paths = sympath.split(";")

    for path in paths:
        path = path.strip()
        if not path:
            continue

        if path.lower().startswith("srv*"):
            parts = path[4:].split("*")
            cache_dir = parts[0] if len(parts) >= 1 else None
            server_url = parts[1] if len(parts) >= 2 else None

            if cache_dir:
                cached = os.path.join(cache_dir, pdb_name, key, pdb_name)
                if os.path.exists(cached):
                    return cached

            if server_url:
                pdb_path = download_pdb_from_server(server_url, pdb_name, key, cache_dir)
                if pdb_path:
                    return pdb_path

        elif path.lower().startswith("cache*"):
            cache_dir = path[6:]
            cached = os.path.join(cache_dir, pdb_name, key, pdb_name)
            if os.path.exists(cached):
                return cached
        else:
            indexed = os.path.join(path, pdb_name, key, pdb_name)
            if os.path.exists(indexed):
                return indexed
            flat = os.path.join(path, pdb_name)
            if os.path.exists(flat):
                return flat

    return None


def download_pdb_from_server(server_url, pdb_name, key, cache_dir):
    url = f"{server_url}/{pdb_name}/{key}/{pdb_name}"
    compressed_url = f"{server_url}/{pdb_name}/{key}/{pdb_name[:-1]}_"

    for try_url in [url, compressed_url]:
        try:
            req = urllib.request.Request(try_url, headers={"User-Agent": "Microsoft-Symbol-Server/10.0"})
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    if cache_dir:
                        dest_dir = os.path.join(cache_dir, pdb_name, key)
                        os.makedirs(dest_dir, exist_ok=True)
                        dest_path = os.path.join(dest_dir, pdb_name)
                        with open(dest_path, "wb") as out:
                            out.write(response.read())
                        if try_url.endswith("_"):
                            try:
                                subprocess.run(["expand", dest_path, dest_path],
                                               capture_output=True, check=True)
                            except (subprocess.CalledProcessError, FileNotFoundError):
                                pass
                        return dest_path
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            continue
    return None


os.environ["PATH"] = WPT_TOOLS_DIR + ";" + os.environ.get("PATH", "")


def find_wpt_tool(tool_name):
    local_path = os.path.join(WPT_TOOLS_DIR, tool_name)
    if os.path.exists(local_path):
        return local_path
    common_paths = [
        rf"C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit\{tool_name}",
        rf"C:\Program Files\Windows Kits\10\Windows Performance Toolkit\{tool_name}",
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path
    try:
        result = subprocess.run(["where", tool_name], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return None


def generate_symcache(pdb_path, pdb_name, key, symcache_root):
    symcache_dir = os.path.join(symcache_root, pdb_name, key)
    os.makedirs(symcache_dir, exist_ok=True)

    symcache_filename = f"{pdb_name}-v3.1.0.symcache"
    symcache_path = os.path.join(symcache_dir, symcache_filename)

    symcachegen = find_wpt_tool("symcachegen.exe")
    if symcachegen:
        env = os.environ.copy()
        env["_NT_SYMCACHE_PATH"] = symcache_root
        cmd = [symcachegen, "-pdb", pdb_path]
        subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=WPT_TOOLS_DIR)

        if os.path.exists(symcache_path):
            return symcache_path
        for f in Path(symcache_dir).glob("*symcache*"):
            return str(f)

    indexed_pdb = os.path.join(symcache_dir, pdb_name)
    if not os.path.exists(indexed_pdb):
        shutil.copy2(pdb_path, indexed_pdb)
    return indexed_pdb


def process_module_for_symcache(module_path, sympath, symcache_root, verbose=True):
    if verbose:
        print(f"Processing: {module_path}")
        print("-" * 60)

    try:
        pdb_name, guid_str, age = read_debug_info_from_pe(module_path)
    except (ValueError, FileNotFoundError, OSError) as e:
        if verbose:
            print(f"ERROR: {e}")
        return False

    key = f"{guid_str}{age:X}"
    if verbose:
        print(f"PDB Name: {pdb_name}")
        print(f"GUID:     {guid_str}")
        print(f"Age:      {age}")
        print(f"Key:      {pdb_name}\\{key}")

    symcache_file = os.path.join(symcache_root, pdb_name, key, f"{pdb_name}-v3.1.0.symcache")
    if os.path.exists(symcache_file):
        if verbose:
            print(f"SymCache already exists: {symcache_file}")
        return True

    if verbose:
        print("Searching for PDB in symbol path...")
    pdb_path = find_pdb_in_sympath(pdb_name, guid_str, age, sympath)
    if not pdb_path:
        if verbose:
            print(f"ERROR: PDB '{pdb_name}' not found in symbol path")
        return False

    if verbose:
        print(f"Found PDB: {pdb_path}")
        print("Generating SymCache...")

    result_path = generate_symcache(pdb_path, pdb_name, key, symcache_root)
    if result_path:
        if verbose:
            print(f"SUCCESS: {result_path}")
        return True
    else:
        if verbose:
            print("FAILED to generate SymCache")
        return False


def get_wpa_profile_path():
    profile_dir = os.path.join(tempfile.gettempdir(), "wpa_hotspot_tool")
    os.makedirs(profile_dir, exist_ok=True)
    profile_path = os.path.join(profile_dir, "cpu_hotspot.wpaProfile")
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write(WPA_PROFILE_XML.strip())
    return profile_path


def normalize_process_name(name):
    name = str(name).strip()
    match = re.match(r'^(.*?\.exe)', name, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return name


# =============================================================================
# CLI Pipeline
# =============================================================================

def run_symcache_step(modules_dir, sympath, symcache_dir=SYMCACHE_DIR, verbose=True):
    print("\n[Step 1/3] Generating SymCache for all modules...")
    pe_files = []
    for f in os.listdir(modules_dir):
        if f.lower().endswith(('.exe', '.dll', '.sys')):
            pe_files.append(os.path.join(modules_dir, f))

    print(f"Found {len(pe_files)} PE modules.")

    succeeded = 0
    failed = 0
    for i, pe_path in enumerate(pe_files, 1):
        if verbose:
            print(f"\n[{i}/{len(pe_files)}] {os.path.basename(pe_path)}")
        success = process_module_for_symcache(pe_path, sympath, symcache_dir, verbose)
        if success:
            succeeded += 1
        else:
            failed += 1

    print(f"\nSymCache summary: {succeeded} succeeded, {failed} failed out of {len(pe_files)} modules.")
    return succeeded > 0


def run_export_step(etl_path, out_csv=None):
    """Export CPU-sampling data from an ETL to CSV via wpaexporter. When out_csv
    is given, the freshly generated CSV is copied there — this lets callers keep
    a baseline and a post-optimization CSV side by side without the two exports
    (which both land in the ETL's folder) overwriting or shadowing each other."""
    print("\n[Step 2/3] Running wpaexporter...")

    wpaexporter = find_wpt_tool("wpaexporter.exe")
    if not wpaexporter:
        print("ERROR: wpaexporter.exe not found.")
        sys.exit(1)

    profile_path = get_wpa_profile_path()
    output_folder = os.path.dirname(os.path.abspath(etl_path))
    # Snapshot pre-existing CSVs so we can identify the one THIS run produces,
    # rather than blindly grabbing csv_files[0] (which may be a stale/other CSV).
    before = {f for f in os.listdir(output_folder) if f.lower().endswith('.csv')}
    cmd = [wpaexporter, "-i", etl_path, "-profile", profile_path,
           "-outputfolder", output_folder, "-symbols"]

    print(f"Command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=WPT_TOOLS_DIR)

    if result.returncode != 0:
        print(f"wpaexporter failed (exit {result.returncode})")
        if result.stderr:
            print(result.stderr)
        sys.exit(1)

    after = [f for f in os.listdir(output_folder) if f.lower().endswith('.csv')]
    new_csvs = [f for f in after if f not in before]
    chosen = new_csvs[0] if new_csvs else (after[0] if after else None)
    if not chosen:
        print("No CSV files generated.")
        sys.exit(1)

    csv_path = os.path.join(output_folder, chosen)
    if out_csv:
        out_csv = os.path.abspath(out_csv)
        if os.path.abspath(csv_path) != out_csv:
            os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
            shutil.copy2(csv_path, out_csv)
        csv_path = out_csv
    print(f"Generated: {csv_path}")
    return csv_path


def load_csv(csv_path):
    print("\n[Step 3/3] Loading CSV...")
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    df['Process'] = df['Process'].apply(normalize_process_name)
    print(f"Loaded {len(df)} rows | {len(df['Process'].unique())} processes")
    return df



def analyze_hotspots(df, process, module, top_n=50):
    filtered = df[df['Process'].str.strip().str.lower() == process.lower()]
    filtered = filtered[filtered['Module'].str.strip().str.lower() == module.lower()]

    if filtered.empty:
        print(f"No entries found for process='{process}', module='{module}'")
        sys.exit(1)

    has_weight = 'Weight (in view)' in filtered.columns
    total = len(filtered)

    if has_weight:
        filtered = filtered.copy()
        filtered['Weight (in view)'] = pd.to_numeric(filtered['Weight (in view)'], errors='coerce').fillna(0)
        func_weight = filtered.groupby('Function')['Weight (in view)'].sum().sort_values(ascending=False)
        total_weight = func_weight.sum()
        sorted_funcs = func_weight.head(top_n)

        func_col_width = max(len('Function'), max(len(str(f)) for f in sorted_funcs.index))
        line_width = 5 + func_col_width + 2 + 12 + 9 + 8
        print(f"\nProcess: {process}  |  Module: {module}  |  Samples: {total}  |  Total Weight: {total_weight:.3f} ms  |  Functions: {len(func_weight)}")
        print(f"\nTop {min(top_n, len(sorted_funcs))} hotspot functions:")
        print("-" * line_width)
        print(f"{'#':<5} {'Function':<{func_col_width}} {'Weight (ms)':>12} {'%':>8} {'Count':>8}")
        print("-" * line_width)

        func_counts = Counter(filtered['Function'])
        for rank, (func, weight) in enumerate(sorted_funcs.items(), 1):
            pct = (weight / total_weight) * 100 if total_weight > 0 else 0
            count = func_counts[func]
            print(f"{rank:<5} {func:<{func_col_width}} {weight:>12.3f} {pct:>7.2f}% {count:>8}")

        print("-" * line_width)
        print(f"{'Total':<{5 + func_col_width}} {total_weight:>12.3f} {'100.00%':>8} {total:>8}")
    else:
        func_counts = Counter(filtered['Function'])
        sorted_funcs = func_counts.most_common(top_n)

        func_col_width = max(len('Function'), max(len(str(f)) for f, _ in sorted_funcs))
        line_width = 5 + func_col_width + 2 + 8 + 8
        print(f"\nProcess: {process}  |  Module: {module}  |  Samples: {total}  |  Functions: {len(func_counts)}")
        print(f"\nTop {min(top_n, len(sorted_funcs))} hotspot functions:")
        print("-" * line_width)
        print(f"{'#':<5} {'Function':<{func_col_width}} {'Count':>8} {'%':>8}")
        print("-" * line_width)

        for rank, (func, count) in enumerate(sorted_funcs, 1):
            pct = (count / total) * 100
            print(f"{rank:<5} {func:<{func_col_width}} {count:>8} {pct:>7.2f}%")

        print("-" * line_width)
        print(f"{'Total':<{5 + func_col_width}} {total:>8} {'100.00%':>8}")


def find_functions_in_source(source_dir):
    """Scan all source files and extract function/label definitions.
    Returns {function_name: (relative_path, line_number)}."""
    HEADER_EXTENSIONS = {'.h', '.hpp', '.hxx'}
    C_LIKE_EXTENSIONS = {'.c', '.cpp', '.cc', '.cxx', '.inl', '.m', '.mm'}
    ASM_EXTENSIONS = {'.s', '.asm', '.S'}
    C_FUNC_RE = re.compile(
        r'^[\w\s\*\(\)_,]*?\b([a-zA-Z_]\w*)\s*\([^;]*$'
    )
    ASM_LABEL_RE = re.compile(r'^(function|ENTRY|GLOBAL|global)\s+(\w+)', re.IGNORECASE)
    ASM_PLAIN_LABEL_RE = re.compile(r'^([a-zA-Z_]\w*):\s*$')

    functions = {}
    source_dir = os.path.abspath(source_dir)

    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in C_LIKE_EXTENSIONS and ext not in ASM_EXTENSIONS and ext not in HEADER_EXTENSIONS:
                continue
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, source_dir)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        stripped = line.strip()
                        if not stripped or stripped.startswith('//') or stripped.startswith('/*'):
                            continue
                        if ext in ASM_EXTENSIONS:
                            m = ASM_LABEL_RE.match(stripped)
                            if m:
                                func_name = m.group(2)
                                if func_name not in functions:
                                    functions[func_name] = (rel_path, line_num)
                                continue
                            m = ASM_PLAIN_LABEL_RE.match(stripped)
                            if m:
                                func_name = m.group(1)
                                if func_name not in functions:
                                    functions[func_name] = (rel_path, line_num)
                                continue
                        else:
                            m = C_FUNC_RE.match(stripped)
                            if m:
                                func_name = m.group(1)
                                if func_name in ('if', 'for', 'while', 'switch', 'return',
                                                 'sizeof', 'typeof', 'defined'):
                                    continue
                                if func_name not in functions:
                                    functions[func_name] = (rel_path, line_num)
            except OSError:
                continue

    return functions


def analyze_hotspots_vs_source(df, source_dir, process=None, top_n=50):
    """Cross-reference hotspot functions against source code."""
    print("\nScanning source code for function definitions...")
    source_funcs = find_functions_in_source(source_dir)
    print(f"Found {len(source_funcs)} function/label definitions in source.")

    filtered = df
    if process:
        filtered = filtered[filtered['Process'].str.strip().str.lower() == process.lower()]
        if filtered.empty:
            print(f"No data found for process: {process}")
            return

    has_weight = 'Weight (in view)' in filtered.columns

    if has_weight:
        filtered = filtered.copy()
        filtered['Weight (in view)'] = pd.to_numeric(filtered['Weight (in view)'], errors='coerce').fillna(0)
        func_weight = filtered.groupby('Function')['Weight (in view)'].sum().sort_values(ascending=False)
    else:
        func_weight = filtered.groupby('Function').size().sort_values(ascending=False)
        func_weight.name = 'Count'

    matched = []
    for func_name, weight in func_weight.items():
        func_name_clean = str(func_name).strip()
        # Strip module prefix (e.g., "lame_enc.dll!lame_encode_buffer" -> "lame_encode_buffer")
        if '!' in func_name_clean:
            func_name_clean = func_name_clean.split('!', 1)[1]
        # Strip C++ class/namespace prefix for matching (e.g., "Class::Method" -> "Method")
        lookup_names = [func_name_clean]
        if '::' in func_name_clean:
            lookup_names.append(func_name_clean.rsplit('::', 1)[1])
        for name in lookup_names:
            if name in source_funcs:
                rel_path, line_num = source_funcs[name]
                matched.append((func_name_clean, weight, rel_path, line_num))
                break

    if not matched:
        print("No hotspot functions matched against the source code.")
        return

    matched = matched[:top_n]
    total_weight = sum(w for _, w, _, _ in matched)

    func_col_width = max(len('Function'), max(len(f) for f, _, _, _ in matched))
    loc_col_width = max(len('Source File:Line'), max(len(f"{rp}:{ln}") for _, _, rp, ln in matched))
    line_width = 5 + func_col_width + 2 + loc_col_width + 2 + 12 + 9

    proc_label = f"Process: {process}  |  " if process else ""
    print(f"\n{proc_label}Matched: {len(matched)} functions  |  Total Weight: {total_weight:.3f} {'ms' if has_weight else 'samples'}")
    print(f"\nTop {len(matched)} hotspot functions (matched against source):")
    print("-" * line_width)
    print(f"{'#':<5} {'Function':<{func_col_width}} {'Source File:Line':<{loc_col_width}} {'Weight':>12} {'%':>8}")
    print("-" * line_width)

    for rank, (func, weight, rel_path, line_num) in enumerate(matched, 1):
        pct = (weight / total_weight) * 100 if total_weight > 0 else 0
        loc = f"{rel_path}:{line_num}"
        if has_weight:
            print(f"{rank:<5} {func:<{func_col_width}} {loc:<{loc_col_width}} {weight:>12.3f} {pct:>7.2f}%")
        else:
            print(f"{rank:<5} {func:<{func_col_width}} {loc:<{loc_col_width}} {int(weight):>12} {pct:>7.2f}%")

    print("-" * line_width)
    total_label_width = 5 + func_col_width + 2 + loc_col_width
    print(f"{'Total':<{total_label_width}} {total_weight:>12.3f} {'100.00%':>8}" if has_weight else
          f"{'Total':<{total_label_width}} {int(total_weight):>12} {'100.00%':>8}")


def check_exit(user_input):
    if user_input.lower() in ('exit', 'quit', 'q'):
        print("\nExiting. Goodbye!")
        sys.exit(0)


# =============================================================================
# Toolchain / Build / Capture / Compare  (project -> exe+pdb -> etl -> validate)
# =============================================================================

TOOLCHAIN_CACHE_REL = r".copilot\state\wos-toolchain.json"


def load_toolchain(project_dir):
    """Read the wos-toolchain-discovery cache (host arch + cl/msbuild/dumpbin/vcvars).
    The wos-etl-hotspot agent runs toolchain discovery first, so the cache should
    exist under <project>\\.copilot\\state\\wos-toolchain.json."""
    import json
    cache = os.path.join(project_dir, TOOLCHAIN_CACHE_REL)
    if not os.path.exists(cache):
        raise FileNotFoundError(
            f"Toolchain cache not found: {cache}\n"
            "Run the wos-toolchain-discovery skill first so this file is populated."
        )
    with open(cache, "r", encoding="utf-8") as f:
        tc = json.load(f)
    for key in ("hostArch", "msbuild", "dumpbin"):
        if not tc.get(key):
            raise ValueError(f"Toolchain cache missing '{key}': {cache}")
    return tc


def detect_build_system(project_dir):
    """Return ('msbuild'|'cmake'|None, primary_target_path)."""
    slns = list(Path(project_dir).rglob("*.sln"))
    if slns:
        return "msbuild", str(slns[0])
    vcxprojs = list(Path(project_dir).rglob("*.vcxproj"))
    if vcxprojs:
        return "msbuild", str(vcxprojs[0])
    if os.path.exists(os.path.join(project_dir, "CMakeLists.txt")):
        return "cmake", os.path.join(project_dir, "CMakeLists.txt")
    return None, None


def run_in_vcvars(vcvars, inner_cmd, cwd):
    """Run a command inside the MSVC developer environment. Building ARM64 with
    cl/msbuild/cmake requires INCLUDE/LIB/PATH set by vcvars*.bat — invoking the
    tools bare (as a plain subprocess) usually fails to find headers/libs. We
    source vcvars and chain the real command in a single cmd.exe /c."""
    quoted = subprocess.list2cmdline(inner_cmd)
    full = f'"{vcvars}" && {quoted}'
    return subprocess.run(["cmd", "/c", full], cwd=cwd)


def run_build(project_dir, config="RelWithDebInfo", platform="ARM64"):
    """Build the project for ARM64 WITH PDBs. Returns modules_dir (folder holding
    the built .exe + .pdb). PDB generation is forced because symbol resolution in
    the analyze step needs it; a plain Release build often omits it."""
    print("\n[build] Detecting build system...")
    tc = load_toolchain(project_dir)
    vcvars = tc.get("vcvars")
    if not vcvars or not os.path.exists(vcvars):
        print(f"ERROR: vcvars script not found in toolchain cache: {vcvars}")
        print("Re-run the wos-toolchain-discovery skill to populate it.")
        sys.exit(1)
    bs, target = detect_build_system(project_dir)
    if not bs:
        print("ERROR: no supported build system found (.sln/.vcxproj/CMakeLists.txt).")
        sys.exit(1)
    print(f"  build system: {bs}   target: {target}")
    print(f"  vcvars: {vcvars}")

    if bs == "msbuild":
        msbuild = tc["msbuild"]
        # /p:DebugType=full + /p:DebugSymbols=true force PDB emission for Release-like builds.
        cmd = [msbuild, target, "/t:Build",
               f"/p:Configuration=Release", f"/p:Platform={platform}",
               "/p:DebugType=full", "/p:DebugSymbols=true", "/m"]
        print(f"  {' '.join(cmd)}")
        r = run_in_vcvars(vcvars, cmd, project_dir)
        if r.returncode != 0:
            print(f"ERROR: msbuild failed (exit {r.returncode}).")
            sys.exit(1)
    else:  # cmake
        arch_flag = "ARM64" if platform.upper() == "ARM64" else platform
        build_dir = os.path.join(project_dir, "build-arm64")
        cfg = [
            "cmake", "-S", project_dir, "-B", build_dir, "-A", arch_flag,
            f"-DCMAKE_BUILD_TYPE={config}",
        ]
        print(f"  {' '.join(cfg)}")
        if run_in_vcvars(vcvars, cfg, project_dir).returncode != 0:
            print("ERROR: cmake configure failed."); sys.exit(1)
        bld = ["cmake", "--build", build_dir, "--config", config, "--parallel"]
        print(f"  {' '.join(bld)}")
        if run_in_vcvars(vcvars, bld, project_dir).returncode != 0:
            print("ERROR: cmake build failed."); sys.exit(1)

    # Locate built .exe + .pdb (co-located). Prefer a folder containing both.
    exes = [p for p in Path(project_dir).rglob("*.exe")]
    modules = None
    for exe in exes:
        if list(exe.parent.glob("*.pdb")):
            modules = str(exe.parent)
            break
    if not modules and exes:
        modules = str(exes[0].parent)
    if not modules:
        print("ERROR: no built .exe found after build.")
        sys.exit(1)
    print(f"  modules_dir (exe + pdb): {modules}")

    # Validate ARM64 machine type with dumpbin (AA64).
    dumpbin = tc.get("dumpbin")
    if dumpbin and os.path.exists(dumpbin):
        for exe in Path(modules).glob("*.exe"):
            out = subprocess.run([dumpbin, "/HEADERS", str(exe)],
                                 capture_output=True, text=True).stdout
            tag = "AA64" if "AA64" in out or "ARM64" in out else "NOT-ARM64"
            print(f"  dumpbin {exe.name}: {tag}")

    # Verify each built exe has a MATCHING co-located PDB. The exe's debug
    # directory names the exact pdb (name + GUID/age); a stale or absent PDB in
    # modules_dir means symbol resolution — and therefore hotspot naming — will
    # silently fail later. Warn per-exe so the agent can rebuild rather than
    # profile an unresolvable binary.
    for exe in Path(modules).glob("*.exe"):
        try:
            pdb_name, guid, age = read_debug_info_from_pe(str(exe))
        except (ValueError, OSError):
            print(f"  WARNING: {exe.name} has no debug directory — no PDB emitted; "
                  f"symbol resolution will fail. Ensure /Zi + /DEBUG (PDBs).")
            continue
        local_pdb = os.path.join(modules, pdb_name)
        if os.path.exists(local_pdb):
            print(f"  PDB match: {exe.name} -> {pdb_name} ({guid}{age:X})")
        else:
            print(f"  WARNING: {exe.name} expects '{pdb_name}' but it is NOT in "
                  f"{modules} — symbol resolution may fail. Rebuild with PDBs.")
    return modules


def _is_admin():
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def detect_workload(modules_dir, target_exe):
    """Auto-detect a workload command to exercise the app during tracing.
    Priority: sibling bench/perf/test exe -> the target exe itself. Returns a
    command list. The last-resort (target exe, no args) is flagged presumed-invalid."""
    cand = []
    for exe in Path(modules_dir).glob("*.exe"):
        name = exe.stem.lower()
        if any(k in name for k in ("bench", "perf")):
            cand.insert(0, (str(exe), [], "benchmark"))
        elif "test" in name:
            cand.append((str(exe), [], "test"))
    if cand:
        exe, args, kind = cand[0]
        return [exe] + args, kind, True
    # last resort: run the target exe with no args (presumed unrepresentative)
    return [target_exe], "target-noargs", False


def run_capture(exe, out_etl, workload=None, hostArch=None, project_dir=None, timeout=300):
    """Capture a CPU ETL trace on ARM64. On x64 hosts, refuses and asks for an
    ARM64-captured ETL instead (can't execute ARM64 binaries to profile them).
    `timeout` bounds the workload run (seconds); tune it for long benchmarks."""
    if hostArch and hostArch.upper() != "ARM64":
        print("=" * 70)
        print("x64 HOST: cannot capture a representative ARM64 trace here.")
        print("Provide an ARM64-captured .etl for THIS build via --etl, or run on")
        print("a native ARM64 device:")
        print(f'  wpr -start CPU -filemode')
        print(f'  <run your workload against {os.path.basename(exe)}>')
        print(f'  wpr -stop "{out_etl}"')
        print("=" * 70)
        sys.exit(2)

    wpr = find_wpt_tool("wpr.exe") or "wpr.exe"
    if not _is_admin():
        print("ERROR: WPR capture requires an elevated (Administrator) shell.")
        print("Re-run this command from an elevated terminal.")
        sys.exit(1)

    modules_dir = os.path.dirname(os.path.abspath(exe))
    if workload:
        wl_cmd = workload if isinstance(workload, list) else [workload]
        wl_kind, representative = "user-supplied", True
    else:
        wl_cmd, wl_kind, representative = detect_workload(modules_dir, exe)
    print(f"[capture] workload ({wl_kind}): {' '.join(wl_cmd)}")
    if not representative:
        print("WARNING: no benchmark/test found — this trace may NOT represent real")
        print("         work. Pass --workload \"<cmd>\" for meaningful hotspots.")

    subprocess.run([wpr, "-cancel"], capture_output=True)  # clear any stale session
    if subprocess.run([wpr, "-start", "CPU", "-filemode"]).returncode != 0:
        print("ERROR: wpr -start failed."); sys.exit(1)
    try:
        subprocess.run(wl_cmd, cwd=modules_dir, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"[capture] workload hit the {timeout}s timeout — stopping trace.")
    except (OSError, FileNotFoundError) as e:
        subprocess.run([wpr, "-cancel"], capture_output=True)
        print(f"ERROR: workload failed to run: {e}"); sys.exit(1)
    if subprocess.run([wpr, "-stop", out_etl]).returncode != 0:
        print("ERROR: wpr -stop failed."); sys.exit(1)
    print(f"[capture] wrote {out_etl}")
    return out_etl


def assert_trace_representative(etl_path, min_kb=100):
    """Cheap first gate: reject an obviously idle/empty ETL by size before export."""
    if not os.path.exists(etl_path):
        print(f"ERROR: ETL not found: {etl_path}"); sys.exit(1)
    kb = os.path.getsize(etl_path) / 1024.0
    if kb < min_kb:
        print(f"ERROR: ETL is only {kb:.0f} KB (< {min_kb} KB) — likely idle or too")
        print("       short to contain CPU samples. Provide a real workload / trace.")
        sys.exit(1)
    print(f"[gate] ETL size OK: {kb:.0f} KB")


def assert_csv_representative(df, process_hint=None, min_rows=100):
    """Stronger gate on the exported CSV (real sample data, not just file size):
    require a floor of CPU-sample rows, and — if the target exe is known — that
    its process actually appears in the trace. This is what stops us from ranking
    'hotspots' out of an idle or wrong-process capture."""
    total = len(df)
    if total < min_rows:
        print(f"ERROR: trace has only {total} CPU-sample rows (< {min_rows}). The run")
        print("       was likely idle or too short. Provide a real --workload, or a")
        print("       longer/representative ARM64 trace, and retry.")
        sys.exit(1)
    if process_hint:
        stem = os.path.splitext(os.path.basename(process_hint))[0].lower()
        procs = {str(p).lower() for p in df['Process'].unique()}
        if not any(stem in p for p in procs):
            print(f"WARNING: target process '{stem}' not found among traced processes:")
            print("         " + ", ".join(sorted(procs)[:12]))
            print("         The workload may not have exercised the built binary.")
    print(f"[gate] trace has {total} CPU-sample rows across "
          f"{len(df['Process'].unique())} processes")


def run_compare(before_csv, after_csv, source_dir=None, top_n=50):
    """Diff per-function CPU weight between a baseline and post-optimization CSV."""
    print("\n[compare] baseline vs post-optimization")
    before = load_csv(before_csv)
    after = load_csv(after_csv)

    def weight_by_func(df):
        if 'Weight (in view)' in df.columns:
            df = df.copy()
            df['Weight (in view)'] = pd.to_numeric(df['Weight (in view)'], errors='coerce').fillna(0)
            return df.groupby('Function')['Weight (in view)'].sum()
        return df.groupby('Function').size()

    wb, wa = weight_by_func(before), weight_by_func(after)
    funcs = sorted(set(wb.index) | set(wa.index),
                   key=lambda f: wb.get(f, 0), reverse=True)[:top_n]
    print(f"\n{'Function':<40} {'Before':>12} {'After':>12} {'Delta %':>10}")
    print("-" * 76)
    for f in funcs:
        b, a = float(wb.get(f, 0)), float(wa.get(f, 0))
        delta = ((a - b) / b * 100) if b else 0.0
        fn = str(f)[:39]
        print(f"{fn:<40} {b:>12.1f} {a:>12.1f} {delta:>9.1f}%")
    print("-" * 76)


def prompt_path(prompt_msg, must_exist=True, is_dir=False):
    while True:
        path = input(prompt_msg).strip().strip('"').strip("'")
        check_exit(path)
        if not path:
            print("  Path cannot be empty. Please try again (or type 'exit' to quit).")
            continue
        if must_exist:
            if is_dir and not os.path.isdir(path):
                print(f"  Directory not found: {path}")
                continue
            elif not is_dir and not os.path.exists(path):
                print(f"  File not found: {path}")
                continue
        return path


def prompt_choice(options, prompt_msg="Select an option"):
    print(f"\n{prompt_msg}:")
    for i, opt in enumerate(options, 1):
        print(f"  [{i}] {opt}")
    print("  Type 'exit' to quit.")
    while True:
        choice = input(f"Enter number (1-{len(options)}): ").strip()
        check_exit(choice)
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        print(f"  Invalid choice. Enter a number between 1 and {len(options)}.")


def main():
    # Subcommand dispatch. Back-compat: if the first token isn't a known
    # subcommand, fall through to the legacy `analyze` pipeline so existing
    # invocations (positional modules_dir + etl) keep working unchanged.
    SUBCOMMANDS = {"analyze", "build", "capture", "compare"}
    argv = sys.argv[1:]
    sub = argv[0] if argv and argv[0] in SUBCOMMANDS else "analyze"
    rest = argv[1:] if (argv and argv[0] in SUBCOMMANDS) else argv

    if sub == "build":
        p = argparse.ArgumentParser(prog="hotspot_analysis.py build")
        p.add_argument("project_dir")
        p.add_argument("--config", default="RelWithDebInfo")
        p.add_argument("--platform", default="ARM64")
        a = p.parse_args(rest)
        modules = run_build(a.project_dir, a.config, a.platform)
        print(f"\nMODULES_DIR={modules}")
        return

    if sub == "capture":
        p = argparse.ArgumentParser(prog="hotspot_analysis.py capture")
        p.add_argument("exe")
        p.add_argument("--out", required=True, help="output .etl path")
        p.add_argument("--workload", help="command to exercise the app (quoted)")
        p.add_argument("--project-dir", help="project dir for toolchain host-arch lookup")
        p.add_argument("--timeout", type=int, default=300,
                       help="max seconds to run the workload during tracing (default: 300)")
        a = p.parse_args(rest)
        hostArch = None
        if a.project_dir:
            try:
                hostArch = load_toolchain(a.project_dir).get("hostArch")
            except (FileNotFoundError, ValueError):
                pass
        wl = a.workload.split() if a.workload else None
        run_capture(a.exe, a.out, workload=wl, hostArch=hostArch,
                    project_dir=a.project_dir, timeout=a.timeout)
        assert_trace_representative(a.out)
        return

    if sub == "compare":
        p = argparse.ArgumentParser(prog="hotspot_analysis.py compare")
        p.add_argument("before_csv")
        p.add_argument("after_csv")
        p.add_argument("--source-dir", "-s")
        p.add_argument("--top", "-n", type=int, default=50)
        a = p.parse_args(rest)
        run_compare(a.before_csv, a.after_csv, a.source_dir, a.top)
        return

    # --- sub == "analyze": legacy pipeline (unchanged behavior) ---
    cmd_analyze(rest)


def cmd_analyze(argv):
    parser = argparse.ArgumentParser(
        prog="hotspot_analysis.py [analyze]",
        description="WPA Hotspot Tool - Generate SymCache, export ETL, analyze CPU hotspots",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Subcommands:
  build    <project_dir> [--config RelWithDebInfo] [--platform ARM64]
  capture  <exe> --out <etl> [--workload "<cmd>"] [--project-dir <dir>]
  compare  <before.csv> <after.csv> [--source-dir <src>]
  analyze  (default) — the classic modules_dir + etl -> hotspot pipeline

Examples:
  # Cross-reference hotspots against source code (default analyze mode)
  python hotspot_analysis.py C:\\modules trace.etl --source-dir C:\\src\\ffmpeg

  # Build a project for ARM64 with PDBs
  python hotspot_analysis.py build C:\\src\\zlib

  # Capture a CPU trace (ARM64 host, elevated)
  python hotspot_analysis.py capture C:\\src\\zlib\\build\\minigzip.exe --out base.etl

  # Compare before/after CSVs
  python hotspot_analysis.py compare base.csv post.csv
""")

    parser.add_argument("modules_dir", nargs="?", help="Folder containing modules (.exe/.dll and .pdbs)")
    parser.add_argument("etl_file", nargs="?", help="ETL trace file")
    parser.add_argument("--csv", help="Use an existing CSV file (skip symcache + export steps)")
    parser.add_argument("--process", "-p", help="Process name to filter")
    parser.add_argument("--module", "-m", help="Module name to filter")
    parser.add_argument("--skip-symcache", action="store_true", help="Skip SymCache generation step")
    parser.add_argument("--skip-export", action="store_true", help="Skip wpaexporter step (use existing CSV)")
    parser.add_argument("--top", "-n", type=int, default=50, help="Number of top functions to show (default: 50)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Reduce output verbosity")
    parser.add_argument("--symcache-dir", default=SYMCACHE_DIR, help=f"SymCache directory (default: {SYMCACHE_DIR})")
    parser.add_argument("--symbol-path", default=SYMBOL_PATH, help="Symbol path override")
    parser.add_argument("--source-dir", "-s", help="Source code directory to match hotspot functions against")
    parser.add_argument("--out-csv", help="Copy the exported CSV to this explicit path (keeps baseline vs post CSVs distinct for `compare`)")
    parser.add_argument("--verify-process", help="Warn if this process (e.g. app.exe) is absent from the trace — guards against tracing the wrong/idle process")

    args = parser.parse_args(argv)

    symcache_dir = args.symcache_dir
    os.makedirs(symcache_dir, exist_ok=True)

    print("=" * 60)
    print("  WPA Hotspot Analysis Tool")
    print("=" * 60)

    # --- Collect all user inputs upfront ---
    print("\n[Input Collection]")

    csv_path = None
    modules_dir = None
    etl_path = None
    source_dir = args.source_dir

    if args.csv:
        if not os.path.exists(args.csv):
            print(f"ERROR: CSV file not found: {args.csv}")
            sys.exit(1)
        csv_path = args.csv
    else:
        # Get modules directory
        modules_dir = args.modules_dir
        if not modules_dir:
            modules_dir = prompt_path("  Modules folder (.exe/.dll and .pdbs): ", must_exist=True, is_dir=True)
        else:
            modules_dir = modules_dir.strip('"').strip("'")
            if not os.path.isdir(modules_dir):
                print(f"ERROR: Modules folder not found: {modules_dir}")
                sys.exit(1)

        # Get ETL file
        etl_path = args.etl_file
        if not etl_path:
            etl_path = prompt_path("  ETL trace file: ", must_exist=True, is_dir=False)
        else:
            etl_path = etl_path.strip('"').strip("'")
            if not os.path.exists(etl_path):
                print(f"ERROR: ETL file not found: {etl_path}")
                sys.exit(1)

    # Get source directory (required)
    if not source_dir:
        source_dir = prompt_path("  Source code directory: ", must_exist=True, is_dir=True)

    print("\n" + "=" * 60)
    print("  All inputs collected. Starting processing...")
    print("=" * 60)

    # --- Run pipeline ---
    if not csv_path:
        sympath = modules_dir + ";" + args.symbol_path
        os.environ["_NT_SYMBOL_PATH"] = sympath
        os.environ["_NT_SYMCACHE_PATH"] = symcache_dir

        print(f"\nSymbol Path: {sympath}")
        print(f"SymCache Dir: {symcache_dir}")

        # Step 1: SymCache
        if not args.skip_symcache:
            run_symcache_step(modules_dir, sympath, symcache_dir, verbose=not args.quiet)

        # Step 2: Export
        if not args.skip_export:
            csv_path = run_export_step(etl_path, out_csv=args.out_csv)
        else:
            output_folder = os.path.dirname(os.path.abspath(etl_path))
            csv_files = [f for f in os.listdir(output_folder) if f.lower().endswith('.csv')]
            if not csv_files:
                print("ERROR: No CSV files found. Run without --skip-export first.")
                sys.exit(1)
            csv_path = os.path.join(output_folder, csv_files[0])
            print(f"Using existing CSV: {csv_path}")

    # --- Load and analyze ---
    df = load_csv(csv_path)
    assert_csv_representative(df, process_hint=args.verify_process)

    processes = sorted(df['Process'].unique())
    print(f"\nComparing all {len(processes)} processes against source code...")
    analyze_hotspots_vs_source(df, source_dir, process=None, top_n=args.top)
    print("\nDone.")
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()