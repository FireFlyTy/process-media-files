"""
Metadata Extractor for Multispectral and Aerial Imagery

Extracts and interprets EXIF, TIFF, XMP, GPS, and proprietary metadata
from images, with special support for MicaSense cameras.
"""

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS, IFD
import xml.etree.ElementTree as ET
import re
from typing import Any
from dataclasses import dataclass, field


# =============================================================================
# INTERPRETATION DICTIONARIES
# =============================================================================

BASIC_INFO_INTERPRETATION = {
    "format": "Image file format (TIFF, JPEG, PNG, etc.)",
    "mode": "Pixel format and bit depth. Common values: 'RGB' (24-bit color), 'L' (8-bit grayscale), 'I;16' (16-bit integer grayscale), 'F' (32-bit float)",
    "size": "Image dimensions as (width, height) in pixels",
}

TIFF_TAGS_INTERPRETATION = {
    "ImageWidth": "Image width in pixels",
    "ImageLength": "Image height in pixels",
    "BitsPerSample": "Bits per pixel channel. 8=standard, 12/14/16=high dynamic range for scientific imaging",
    "Compression": "Compression type. 1=none, 5=LZW, 6=JPEG, 7=JPEG2000, 8=deflate",
    "PhotometricInterpretation": "Color space interpretation. 0=WhiteIsZero, 1=BlackIsZero, 2=RGB, 3=Palette, 6=YCbCr",
    "FillOrder": "Bit order within bytes. 1=MSB first (standard), 2=LSB first",
    "SamplesPerPixel": "Number of channels per pixel. 1=grayscale, 3=RGB, 4=RGBA",
    "RowsPerStrip": "Number of rows per strip for strip-based storage",
    "StripOffsets": "Byte offsets to each strip in the file",
    "StripByteCounts": "Size in bytes of each strip",
    "PlanarConfiguration": "Data organization. 1=chunky (RGBRGB), 2=planar (RRR...GGG...BBB)",
    "Orientation": "Image orientation. 1=normal, 3=rotated 180°, 6=rotated 90° CW, 8=rotated 90° CCW",
    "NewSubfileType": "Subfile type. 0=full resolution, 1=reduced resolution, 2=single page of multi-page",
    "XResolution": "Horizontal resolution in ResolutionUnit",
    "YResolution": "Vertical resolution in ResolutionUnit",
    "ResolutionUnit": "Resolution unit. 1=none, 2=inches (DPI), 3=centimeters",
    "Software": "Software/firmware used to create the image",
    "DateTime": "Date and time of image creation (local time)",
    "Artist": "Creator of the image",
    "Copyright": "Copyright information",
    "ExifOffset": "Offset to EXIF IFD",
}

DNG_TAGS_INTERPRETATION = {
    "DNGVersion": "DNG specification version (major.minor.patch.revision)",
    "DNGBackwardVersion": "Minimum DNG reader version required",
    "UniqueCameraModel": "Unique camera identifier for color profile matching",
    "BlackLevelRepeatDim": "Pattern size for black level values (rows, cols)",
    "BlackLevel": "Black level values per pattern cell. Subtract from raw values for calibration",
    "WhiteLevel": "Maximum valid pixel value (saturation point)",
    "ColorMatrix1": "XYZ to camera color space transformation matrix (illuminant 1)",
    "ColorMatrix2": "XYZ to camera color space transformation matrix (illuminant 2)",
    "AsShotNeutral": "White balance coefficients as shot",
    "BaselineExposure": "Exposure compensation in EV",
    "BaselineNoise": "Relative noise level",
    "BaselineSharpness": "Relative sharpness",
    "OpcodeList1": "Opcodes to apply before demosaicing",
    "OpcodeList2": "Opcodes to apply after demosaicing",
    "OpcodeList3": "Opcodes to apply after mapping to output color space",
}

EXIF_TAGS_INTERPRETATION = {
    # Exposure settings (critical for radiometric calibration)
    "ExposureTime": "Exposure duration in seconds. Used in radiance calculation",
    "FNumber": "F-stop (aperture). Lower = wider aperture, more light",
    "ExposureProgram": "Exposure mode. 0=undefined, 1=manual, 2=auto, 3=aperture priority, 4=shutter priority",
    "ISOSpeedRatings": "ISO sensitivity. Gain = ISOSpeedRatings / 100 for MicaSense",
    "ISOSpeed": "Alternative ISO tag. Gain = ISOSpeed / 100 for MicaSense",
    
    # Timestamps
    "DateTimeOriginal": "Date/time when original image was taken",
    "DateTimeDigitized": "Date/time when image was digitized",
    
    # Exposure values (APEX system)
    "ShutterSpeedValue": "Shutter speed in APEX units. Exposure = 2^(-ShutterSpeedValue)",
    "ApertureValue": "Aperture in APEX units. F-number = 2^(ApertureValue/2)",
    "BrightnessValue": "Brightness in APEX units",
    "ExposureBiasValue": "Exposure compensation in EV",
    "MaxApertureValue": "Maximum lens aperture in APEX units",
    
    # Metering and light
    "MeteringMode": "Metering mode. 1=average, 2=center-weighted, 3=spot, 4=multi-spot, 5=pattern",
    "LightSource": "Light source. 0=auto, 1=daylight, 2=fluorescent, 3=tungsten, 9=fine weather",
    "Flash": "Flash status and mode (bit field)",
    
    # Lens
    "FocalLength": "Focal length in mm",
    "FocalLengthIn35mmFilm": "Equivalent focal length for 35mm film",
    
    # Sensor
    "SensingMethod": "Sensor type. 1=undefined, 2=one-chip color, 3=two-chip, 4=three-chip, 5=color sequential",
    "FileSource": "Image source. 1=film scanner, 2=reflection print scanner, 3=digital camera",
    "SceneType": "Scene type. 1=directly photographed",
    
    # Processing
    "WhiteBalance": "White balance mode. 0=auto, 1=manual",
    "DigitalZoomRatio": "Digital zoom ratio",
    "SceneCaptureType": "Scene capture type. 0=standard, 1=landscape, 2=portrait, 3=night",
    "GainControl": "Gain control. 0=none, 1=low gain up, 2=high gain up, 3=low gain down, 4=high gain down",
    "Contrast": "Contrast. 0=normal, 1=soft, 2=hard",
    "Saturation": "Saturation. 0=normal, 1=low, 2=high",
    "Sharpness": "Sharpness. 0=normal, 1=soft, 2=hard",
    "SubjectDistanceRange": "Subject distance range. 0=unknown, 1=macro, 2=close, 3=distant",
    "ImageUniqueID": "Unique image identifier",
    "ExifVersion": "EXIF version",
    "ComponentsConfiguration": "Pixel components configuration",
}

GPS_TAGS_INTERPRETATION = {
    "GPSVersionID": "GPS tag version (typically 2.2.0.0)",
    "GPSLatitudeRef": "Latitude reference: 'N' (north) or 'S' (south)",
    "GPSLatitude": "Latitude as (degrees, minutes, seconds)",
    "GPSLongitudeRef": "Longitude reference: 'E' (east) or 'W' (west)",
    "GPSLongitude": "Longitude as (degrees, minutes, seconds)",
    "GPSAltitudeRef": "Altitude reference: 0=above sea level, 1=below sea level",
    "GPSAltitude": "Altitude in meters",
    "GPSTimeStamp": "UTC time as (hours, minutes, seconds)",
    "GPSSatellites": "Satellites used for measurement",
    "GPSStatus": "Receiver status: 'A'=active, 'V'=void",
    "GPSMeasureMode": "Measurement mode: '2'=2D, '3'=3D",
    "GPSDOP": "Dilution of Precision. Lower=better. <1=RTK quality, 1-2=excellent, 2-5=good",
    "GPSSpeedRef": "Speed unit: 'K'=km/h, 'M'=mph, 'N'=knots",
    "GPSSpeed": "Ground speed",
    "GPSTrackRef": "Track direction reference: 'T'=true north, 'M'=magnetic north",
    "GPSTrack": "Direction of movement in degrees",
    "GPSImgDirectionRef": "Image direction reference: 'T'=true north, 'M'=magnetic north",
    "GPSImgDirection": "Direction the camera was facing in degrees",
    "GPSMapDatum": "Geodetic datum (e.g., 'WGS-84')",
    "GPSDateStamp": "UTC date as 'YYYY:MM:DD'",
    "GPSHPositioningError": "Horizontal positioning error in meters",
}

CAMERA_XMP_INTERPRETATION = {
    # Rig and band identification
    "RigName": "Multi-camera rig identifier (e.g., 'Altum-PT', 'RedEdge-MX')",
    "BandName": "Spectral band name: 'Blue', 'Green', 'Red', 'Red edge', 'NIR', 'Panchro', 'LWIR'",
    "CentralWavelength": "Center wavelength of spectral band in nanometers",
    "WavelengthFWHM": "Full Width at Half Maximum - spectral bandwidth in nm",
    
    # Camera model and optics
    "ModelType": "Camera projection model: 'perspective' (pinhole), 'fisheye', etc.",
    "PrincipalPoint": "Optical center offset from image center in mm (x, y)",
    "PerspectiveFocalLength": "Focal length in specified units",
    "PerspectiveFocalLengthUnits": "Units for focal length (typically 'mm')",
    "PerspectiveDistortion": "Lens distortion coefficients [k1, k2, k3, p1, p2] (Brown-Conrady model). Negative k1 = barrel distortion",
    
    # Vignetting correction (two models: radial polynomial and 2D polynomial)
    "VignettingCenter": "Vignette center point (cx, cy) in pixels for radial model",
    "VignettingPolynomial": "Radial vignette polynomial coefficients [k0-k5]. V(r) = 1 + k0*r + k1*r² + ... + k5*r⁶",
    "VignettingPolynomial2DName": "Indices for 2D vignetting polynomial terms (newer Altum-PT/RedEdge-P)",
    "VignettingPolynomial2D": "Coefficients for 2D vignetting correction across image field",
    
    # Band sensitivity and calibration
    "BandSensitivity": "Relative sensitivity of this band for inter-band normalization",
    
    # Multi-camera rig geometry
    "RigCameraIndex": "Index of this camera in multi-camera rig (0-based)",
    "RigRelativesReferenceRigCameraIndex": "Reference camera index for relative positioning",
    "RigRelatives": "Relative rotation angles to reference camera",
    "RigTranslations": "Physical offset from reference camera in mm [x, y, z]",
    "RigTranslationsUnits": "Units for rig translations (typically 'mm')",
    
    # Camera orientation (attitude)
    "Yaw": "Camera heading/azimuth in degrees (0-360, 0=North, 90=East)",
    "Pitch": "Camera tilt from horizontal in degrees (negative=pointing down)",
    "Roll": "Camera rotation around optical axis in degrees",
    
    # GPS accuracy (RTK/PPK systems)
    "GPSXYAccuracy": "Horizontal positioning accuracy in meters (RTK: <0.02m)",
    "GPSZAccuracy": "Vertical positioning accuracy in meters (RTK: <0.03m)",
    
    # Irradiance at capture (from DLS or internal sensor)
    "Irradiance": "Incident spectral irradiance at sensor in W/m²/μm",
    "IrradianceYaw": "Sensor orientation (yaw) when irradiance was measured in degrees",
    "IrradiancePitch": "Sensor orientation (pitch) when irradiance was measured in degrees",
    "IrradianceRoll": "Sensor orientation (roll) when irradiance was measured in degrees",
    
    # Panel calibration (auto-detected calibration images)
    "AutoCalibrationImage": "Boolean: True if this is a calibration panel image",
    "PanelAlbedo": "Reflectance panel albedo value calculated by camera (0-1)",
    "CalibrationPanelDetected": "Boolean: True if calibration panel was detected in image",
}

MICASENSE_XMP_INTERPRETATION = {
    # Radiometric calibration
    "RadiometricCalibration": "Calibration coefficients [a1, a2, a3] for radiance: L = V(x,y) × (a1 + a2×DN + a3×DN²) / (ExposureTime × Gain)",
    
    # Sensor state
    "ImagerTemperatureC": "Sensor temperature in Celsius for dark current correction",
    "SensorTemperature": "Alternative tag for sensor temperature (some firmware versions)",
    
    # Flight/capture identification
    "FlightId": "Unique identifier for the flight/mission session",
    "CaptureId": "Unique identifier for simultaneous multi-band capture (same across all bands)",
    
    # Capture method
    "TriggerMethod": "Capture trigger source: 0=unknown, 1=timer, 2=manual, 3=external, 4=wifi, 5=software, 6=flight controller",
    
    # Altitude
    "PressureAlt": "Barometric altitude in meters (0 if not available or invalid)",
    
    # Dark level calibration
    "DarkRowValue": "Optically masked pixel values for black level calibration (array of 4 values)",
    
    # Timing
    "BootTimestamp": "Ticks since camera boot for inter-camera synchronization",
    
    # LWIR/Thermal specific (Altum, Altum-PT)
    "ThermalCalibration": "Thermal sensor calibration coefficients",
    "LwirSceneEmissivity": "Scene emissivity setting for thermal calculation (0-1, typically 0.95)",
    "LwirReflectedTemperature": "Reflected temperature setting for thermal calculation in Celsius",
    "LwirWindowTransmission": "Window transmission factor for thermal calculation",
    "LwirWindowTemperature": "Window temperature for thermal calculation in Celsius",
    
    # Panchromatic specific (RedEdge-P, Altum-PT)
    "PanchromaticCalibration": "Panchromatic sensor specific calibration data",
}

DLS_XMP_INTERPRETATION = {
    # DLS identification
    "Serial": "DLS (Downwelling Light Sensor) serial number",
    "SwVersion": "DLS firmware version",
    
    # Spectral configuration
    "CenterWavelength": "DLS spectral band center wavelength in nm",
    "Bandwidth": "DLS spectral bandwidth (FWHM) in nm",
    
    # Timing
    "TimeStamp": "DLS measurement timestamp for camera sync (ticks)",
    
    # Irradiance measurements (DLS2 provides all, DLS1 only SpectralIrradiance)
    "SpectralIrradiance": "Raw irradiance on tilted sensor surface in W/m²/nm (use HorizontalIrradiance for DLS2)",
    "HorizontalIrradiance": "Irradiance on horizontal surface in W/m²/nm (DLS2 only, preferred)",
    "DirectIrradiance": "Direct solar irradiance component in W/m²/nm (DLS2 only)",
    "ScatteredIrradiance": "Diffuse/scattered sky irradiance in W/m²/nm (DLS2 only)",
    
    # Sun position
    "SolarElevation": "Sun elevation angle above horizon in radians",
    "SolarAzimuth": "Sun azimuth angle in radians (0=North, π/2=East)",
    "EstimatedDirectLightVector": "Unit vector pointing toward sun in local NED frame [x, y, z]",
    
    # DLS orientation (IMU)
    "Yaw": "DLS orientation yaw in radians",
    "Pitch": "DLS orientation pitch in radians",
    "Roll": "DLS orientation roll in radians",
    
    # Raw sensor values (advanced)
    "RawMeasurement": "Raw DLS sensor values before processing",
    "Gain": "DLS sensor gain setting",
    "ExposureTime": "DLS sensor exposure time",
}

PROPRIETARY_TAGS_INTERPRETATION = {
    48020: "MicaSense packed metadata structure",
    48021: "MicaSense numeric data: [0, irradiance, timestamp, wavelength, bandwidth, ...]",
    48022: "MicaSense identifiers string: 'CaptureId|FlightId|DLS_Serial'",
}


# =============================================================================
# MICASENSE CAMERA SPECIFICATIONS
# =============================================================================

MICASENSE_CAMERA_SPECS = {
    "ALTUM-PT": {
        "description": "Multispectral + Thermal + Panchromatic sensor",
        "bands": {
            0: {"name": "Blue", "wavelength": 475, "bandwidth": 32},
            1: {"name": "Green", "wavelength": 560, "bandwidth": 27},
            2: {"name": "Red", "wavelength": 668, "bandwidth": 14},
            3: {"name": "Red edge", "wavelength": 717, "bandwidth": 12},
            4: {"name": "NIR", "wavelength": 842, "bandwidth": 57},
            5: {"name": "Panchro", "wavelength": None, "bandwidth": None, "type": "panchromatic"},
            6: {"name": "LWIR", "wavelength": "7.5-13.5 μm", "bandwidth": None, "type": "thermal"},
        },
        "resolution_ms": (2064, 1544),  # 3.2 MP per MS band
        "resolution_pan": (4112, 3008),  # 12 MP panchromatic
        "resolution_thermal": (320, 256),
        "dls_version": "DLS2",
        "has_panchromatic": True,
        "has_thermal": True,
    },
    "ALTUM": {
        "description": "Multispectral + Thermal sensor",
        "bands": {
            0: {"name": "Blue", "wavelength": 475, "bandwidth": 32},
            1: {"name": "Green", "wavelength": 560, "bandwidth": 27},
            2: {"name": "Red", "wavelength": 668, "bandwidth": 14},
            3: {"name": "Red edge", "wavelength": 717, "bandwidth": 12},
            4: {"name": "NIR", "wavelength": 842, "bandwidth": 57},
            5: {"name": "LWIR", "wavelength": "8-14 μm", "bandwidth": None, "type": "thermal"},
        },
        "resolution_ms": (2064, 1544),
        "resolution_thermal": (160, 120),
        "dls_version": "DLS2",
        "has_panchromatic": False,
        "has_thermal": True,
    },
    "REDEDGE-P": {
        "description": "Multispectral + Panchromatic sensor",
        "bands": {
            0: {"name": "Blue", "wavelength": 475, "bandwidth": 32},
            1: {"name": "Green", "wavelength": 560, "bandwidth": 27},
            2: {"name": "Red", "wavelength": 668, "bandwidth": 14},
            3: {"name": "Red edge", "wavelength": 717, "bandwidth": 12},
            4: {"name": "NIR", "wavelength": 842, "bandwidth": 57},
            5: {"name": "Panchro", "wavelength": None, "bandwidth": None, "type": "panchromatic"},
        },
        "resolution_ms": (2064, 1544),
        "resolution_pan": (4112, 3008),
        "dls_version": "DLS2",
        "has_panchromatic": True,
        "has_thermal": False,
    },
    "REDEDGE-MX": {
        "description": "5-band multispectral sensor",
        "bands": {
            0: {"name": "Blue", "wavelength": 475, "bandwidth": 32},
            1: {"name": "Green", "wavelength": 560, "bandwidth": 27},
            2: {"name": "Red", "wavelength": 668, "bandwidth": 14},
            3: {"name": "Red edge", "wavelength": 717, "bandwidth": 12},
            4: {"name": "NIR", "wavelength": 842, "bandwidth": 57},
        },
        "resolution_ms": (1280, 960),
        "dls_version": "DLS2",
        "has_panchromatic": False,
        "has_thermal": False,
    },
    "REDEDGE-MX-DUAL": {
        "description": "10-band dual multispectral sensor",
        "bands": {
            # Camera 1 (master)
            0: {"name": "Blue", "wavelength": 475, "bandwidth": 32},
            1: {"name": "Green", "wavelength": 560, "bandwidth": 27},
            2: {"name": "Red", "wavelength": 668, "bandwidth": 14},
            3: {"name": "Red edge", "wavelength": 717, "bandwidth": 12},
            4: {"name": "NIR", "wavelength": 842, "bandwidth": 57},
            # Camera 2 (auxiliary)
            5: {"name": "Blue-444", "wavelength": 444, "bandwidth": 28},
            6: {"name": "Green-531", "wavelength": 531, "bandwidth": 14},
            7: {"name": "Red-650", "wavelength": 650, "bandwidth": 16},
            8: {"name": "Red edge-705", "wavelength": 705, "bandwidth": 10},
            9: {"name": "Red edge-740", "wavelength": 740, "bandwidth": 18},
        },
        "resolution_ms": (1280, 960),
        "dls_version": "DLS2",
        "has_panchromatic": False,
        "has_thermal": False,
        "is_dual": True,
    },
    "REDEDGE-M": {
        "description": "5-band multispectral sensor (legacy)",
        "bands": {
            0: {"name": "Blue", "wavelength": 475, "bandwidth": 20},
            1: {"name": "Green", "wavelength": 560, "bandwidth": 20},
            2: {"name": "Red", "wavelength": 668, "bandwidth": 10},
            3: {"name": "Red edge", "wavelength": 717, "bandwidth": 10},
            4: {"name": "NIR", "wavelength": 840, "bandwidth": 40},
        },
        "resolution_ms": (1280, 960),
        "dls_version": "DLS1",
        "has_panchromatic": False,
        "has_thermal": False,
    },
}


def get_camera_specs(model_name: str) -> dict:
    """
    Get camera specifications for a MicaSense camera model.
    
    Args:
        model_name: Camera model from EXIF (e.g., 'Altum-PT', 'RedEdge-MX')
        
    Returns:
        Camera specifications dictionary or empty dict if not found
    """
    # Normalize model name
    normalized = model_name.upper().replace(" ", "-").replace("_", "-")
    
    # Handle variations
    if "ALTUM" in normalized and "PT" in normalized:
        return MICASENSE_CAMERA_SPECS.get("ALTUM-PT", {})
    elif "ALTUM" in normalized:
        return MICASENSE_CAMERA_SPECS.get("ALTUM", {})
    elif "REDEDGE" in normalized and "P" in normalized and "MX" not in normalized:
        return MICASENSE_CAMERA_SPECS.get("REDEDGE-P", {})
    elif "REDEDGE" in normalized and "DUAL" in normalized:
        return MICASENSE_CAMERA_SPECS.get("REDEDGE-MX-DUAL", {})
    elif "REDEDGE" in normalized and "MX" in normalized:
        return MICASENSE_CAMERA_SPECS.get("REDEDGE-MX", {})
    elif "REDEDGE" in normalized and "M" in normalized:
        return MICASENSE_CAMERA_SPECS.get("REDEDGE-M", {})
    
    return {}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class MetadataGroups:
    """Container for grouped metadata with interpretation support."""
    
    basic_info: dict = field(default_factory=dict)
    tiff_structure: dict = field(default_factory=dict)
    dng_calibration: dict = field(default_factory=dict)
    exif_camera: dict = field(default_factory=dict)
    gps_location: dict = field(default_factory=dict)
    xmp_camera: dict = field(default_factory=dict)
    xmp_micasense: dict = field(default_factory=dict)
    xmp_dls: dict = field(default_factory=dict)
    proprietary: dict = field(default_factory=dict)
    unknown: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to nested dictionary."""
        return {
            "basic_info": self.basic_info,
            "tiff_structure": self.tiff_structure,
            "dng_calibration": self.dng_calibration,
            "exif_camera": self.exif_camera,
            "gps_location": self.gps_location,
            "xmp_camera": self.xmp_camera,
            "xmp_micasense": self.xmp_micasense,
            "xmp_dls": self.xmp_dls,
            "proprietary": self.proprietary,
            "unknown": self.unknown,
        }
    
    def to_flat_dict(self) -> dict:
        """Convert to flat dictionary with group prefixes."""
        result = {}
        for group_name, group_data in self.to_dict().items():
            for key, value in group_data.items():
                result[f"{group_name}.{key}"] = value
        return result


# =============================================================================
# TAG CLASSIFICATION
# =============================================================================

# TIFF baseline tags
TIFF_TAG_NAMES = {
    "ImageWidth", "ImageLength", "BitsPerSample", "Compression",
    "PhotometricInterpretation", "FillOrder", "SamplesPerPixel",
    "RowsPerStrip", "StripOffsets", "StripByteCounts", "PlanarConfiguration",
    "Orientation", "NewSubfileType", "XResolution", "YResolution",
    "ResolutionUnit", "Software", "DateTime", "Artist", "Copyright",
    "Make", "Model", "ExifOffset",
}

# DNG-specific tags
DNG_TAG_NAMES = {
    "DNGVersion", "DNGBackwardVersion", "UniqueCameraModel",
    "BlackLevelRepeatDim", "BlackLevel", "WhiteLevel",
    "ColorMatrix1", "ColorMatrix2", "AsShotNeutral",
    "BaselineExposure", "BaselineNoise", "BaselineSharpness",
    "OpcodeList1", "OpcodeList2", "OpcodeList3",
    "DefaultCropOrigin", "DefaultCropSize", "CalibrationIlluminant1",
    "CalibrationIlluminant2", "CameraCalibration1", "CameraCalibration2",
}

# EXIF camera/exposure tags
EXIF_TAG_NAMES = {
    "ExposureTime", "FNumber", "ExposureProgram", "ISOSpeedRatings",
    "DateTimeOriginal", "DateTimeDigitized", "ShutterSpeedValue",
    "ApertureValue", "BrightnessValue", "ExposureBiasValue",
    "MaxApertureValue", "MeteringMode", "LightSource", "Flash",
    "FocalLength", "FocalLengthIn35mmFilm", "SensingMethod",
    "FileSource", "SceneType", "WhiteBalance", "DigitalZoomRatio",
    "SceneCaptureType", "GainControl", "Contrast", "Saturation", "Sharpness",
    "SubjectDistanceRange", "ImageUniqueID", "ExifVersion", "ComponentsConfiguration",
}

# Known proprietary tag IDs
PROPRIETARY_TAG_IDS = {48020, 48021, 48022}


# =============================================================================
# XMP PARSING
# =============================================================================

def parse_xmp_packet(xmp_bytes: bytes) -> dict:
    """
    Parse XMP XML packet into structured dictionaries by namespace.
    
    Args:
        xmp_bytes: Raw XMP data as bytes
        
    Returns:
        Dictionary with keys 'camera', 'micasense', 'dls' containing parsed values
    """
    result = {
        "camera": {},
        "micasense": {},
        "dls": {},
    }
    
    if not xmp_bytes:
        return result
    
    try:
        # Decode bytes to string
        if isinstance(xmp_bytes, bytes):
            xmp_str = xmp_bytes.decode('utf-8', errors='ignore')
        else:
            xmp_str = str(xmp_bytes)
        
        # Extract XML content between xmpmeta tags
        match = re.search(r'<x:xmpmeta[^>]*>(.*?)</x:xmpmeta>', xmp_str, re.DOTALL)
        if not match:
            return result
        
        # Define namespaces
        namespaces = {
            'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
            'Camera': 'http://pix4d.com/camera/1.0',
            'MicaSense': 'http://micasense.com/MicaSense/1.0/',
            'DLS': 'http://micasense.com/DLS/1.0/',
        }
        
        # Parse XML
        root = ET.fromstring(f'<root xmlns:x="adobe:ns:meta/">{match.group(0)}</root>')
        
        # Find all rdf:Description elements
        for desc in root.iter('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description'):
            # Process Camera namespace
            for elem in desc:
                tag_local = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                namespace = elem.tag.split('}')[0].replace('{', '') if '}' in elem.tag else ''
                
                # Get value - could be text or nested Seq
                value = _extract_xmp_value(elem, namespaces)
                
                # Route to appropriate dictionary based on namespace
                if 'pix4d.com/camera' in namespace:
                    result["camera"][tag_local] = value
                elif 'micasense.com/MicaSense' in namespace:
                    result["micasense"][tag_local] = value
                elif 'micasense.com/DLS' in namespace:
                    result["dls"][tag_local] = value
        
        # Post-process numeric values
        for group in result.values():
            for key, value in list(group.items()):
                group[key] = _convert_xmp_value(value)
                
    except Exception as e:
        result["_parse_error"] = str(e)
    
    return result


def _extract_xmp_value(elem: ET.Element, namespaces: dict) -> Any:
    """Extract value from XMP element, handling Seq containers."""
    # Check for rdf:Seq child
    seq = elem.find('rdf:Seq', namespaces)
    if seq is not None:
        items = []
        for li in seq.findall('rdf:li', namespaces):
            items.append(li.text if li.text else '')
        return items if len(items) > 1 else (items[0] if items else '')
    
    # Simple text value
    return elem.text if elem.text else ''


def _convert_xmp_value(value: Any) -> Any:
    """Convert string values to appropriate Python types."""
    if isinstance(value, list):
        return [_convert_xmp_value(v) for v in value]
    
    if not isinstance(value, str):
        return value
    
    # Try numeric conversion
    try:
        if '.' in value or 'e' in value.lower():
            return float(value)
        return int(value)
    except (ValueError, TypeError):
        pass
    
    # Try comma-separated values
    if ',' in value and not value.startswith('{'):
        parts = [p.strip() for p in value.split(',')]
        try:
            return [float(p) for p in parts]
        except ValueError:
            return parts
    
    return value


# =============================================================================
# GPS UTILITIES
# =============================================================================

def convert_gps_to_decimal(gps_coords: tuple, ref: str) -> float:
    """
    Convert GPS coordinates from DMS to decimal degrees.
    
    Args:
        gps_coords: Tuple of (degrees, minutes, seconds)
        ref: Reference direction ('N', 'S', 'E', 'W')
        
    Returns:
        Decimal degrees (negative for S/W)
    """
    if not gps_coords or len(gps_coords) < 3:
        return None
    
    degrees = float(gps_coords[0])
    minutes = float(gps_coords[1])
    seconds = float(gps_coords[2])
    
    decimal = degrees + minutes / 60 + seconds / 3600
    
    if ref in ('S', 'W'):
        decimal = -decimal
    
    return round(decimal, 8)


def format_gps_readable(lat: float, lon: float) -> str:
    """Format decimal coordinates as human-readable string."""
    lat_dir = 'N' if lat >= 0 else 'S'
    lon_dir = 'E' if lon >= 0 else 'W'
    return f"{abs(lat):.6f}°{lat_dir}, {abs(lon):.6f}°{lon_dir}"


# =============================================================================
# MAIN EXTRACTION FUNCTION
# =============================================================================

def extract_grouped_metadata(image_path: str) -> MetadataGroups:
    """
    Extract all metadata from an image file, organized into logical groups.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        MetadataGroups object with categorized metadata
    """
    img = Image.open(image_path)
    groups = MetadataGroups()
    
    # -------------------------------------------------------------------------
    # Basic image info
    # -------------------------------------------------------------------------
    groups.basic_info = {
        "format": img.format,
        "mode": img.mode,
        "size": img.size,
        "width": img.size[0],
        "height": img.size[1],
    }
    
    # -------------------------------------------------------------------------
    # EXIF and TIFF tags
    # -------------------------------------------------------------------------
    exif_data = img.getexif()
    xmp_data = None
    
    if exif_data:
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, tag_id)
            
            # Store XMP for later parsing
            if tag_name == "XMLPacket":
                xmp_data = value
                continue
            
            # Classify tag into appropriate group
            if isinstance(tag_name, int) or tag_id in PROPRIETARY_TAG_IDS:
                # Proprietary/unknown numeric tags
                groups.proprietary[tag_id] = _sanitize_value(value)
            elif tag_name in DNG_TAG_NAMES:
                groups.dng_calibration[tag_name] = _sanitize_value(value)
            elif tag_name in TIFF_TAG_NAMES:
                groups.tiff_structure[tag_name] = _sanitize_value(value)
            elif tag_name in EXIF_TAG_NAMES:
                groups.exif_camera[tag_name] = _sanitize_value(value)
            else:
                groups.unknown[str(tag_name)] = _sanitize_value(value)
    
    # -------------------------------------------------------------------------
    # GPS data (separate IFD)
    # -------------------------------------------------------------------------
    if exif_data:
        gps_ifd = exif_data.get_ifd(IFD.GPSInfo)
        if gps_ifd:
            for tag_id, value in gps_ifd.items():
                tag_name = GPSTAGS.get(tag_id, tag_id)
                groups.gps_location[tag_name] = _sanitize_value(value)
            
            # Add computed decimal coordinates
            if "GPSLatitude" in groups.gps_location and "GPSLongitude" in groups.gps_location:
                lat = convert_gps_to_decimal(
                    groups.gps_location.get("GPSLatitude"),
                    groups.gps_location.get("GPSLatitudeRef", "N")
                )
                lon = convert_gps_to_decimal(
                    groups.gps_location.get("GPSLongitude"),
                    groups.gps_location.get("GPSLongitudeRef", "E")
                )
                if lat is not None and lon is not None:
                    groups.gps_location["_latitude_decimal"] = lat
                    groups.gps_location["_longitude_decimal"] = lon
                    groups.gps_location["_coordinates_readable"] = format_gps_readable(lat, lon)
    
    # -------------------------------------------------------------------------
    # EXIF sub-IFD (additional camera data)
    # -------------------------------------------------------------------------
    if exif_data:
        try:
            exif_ifd = exif_data.get_ifd(IFD.Exif)
            if exif_ifd:
                for tag_id, value in exif_ifd.items():
                    tag_name = TAGS.get(tag_id, str(tag_id))
                    groups.exif_camera[tag_name] = _sanitize_value(value)
        except Exception:
            pass
    
    # -------------------------------------------------------------------------
    # XMP metadata
    # -------------------------------------------------------------------------
    if xmp_data:
        xmp_parsed = parse_xmp_packet(xmp_data)
        groups.xmp_camera = xmp_parsed.get("camera", {})
        groups.xmp_micasense = xmp_parsed.get("micasense", {})
        groups.xmp_dls = xmp_parsed.get("dls", {})
    
    img.close()
    return groups


def _sanitize_value(value: Any) -> Any:
    """Convert bytes and other non-serializable types to strings/lists."""
    from PIL.TiffImagePlugin import IFDRational

    # Handle IFDRational (EXIF fractions)
    if isinstance(value, IFDRational):
        # Convert to float or keep as fraction string
        if value.denominator == 1:
            return int(value.numerator)
        return float(value)

    if isinstance(value, bytes):
        try:
            decoded = value.decode('utf-8')
            if decoded.isprintable():
                return decoded
        except UnicodeDecodeError:
            pass
        if len(value) <= 32:
            return value.hex()
        return f"<{len(value)} bytes>"

    if isinstance(value, tuple):
        return [_sanitize_value(v) for v in value]  # Recursively sanitize

    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]

    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}

    return value

# =============================================================================
# INTERPRETATION HELPERS
# =============================================================================

def get_interpretation(group_name: str, tag_name: str) -> str:
    """
    Get human-readable interpretation for a metadata tag.
    
    Args:
        group_name: Name of the metadata group
        tag_name: Name of the tag
        
    Returns:
        Interpretation string or empty string if not found
    """
    interpretation_maps = {
        "basic_info": BASIC_INFO_INTERPRETATION,
        "tiff_structure": TIFF_TAGS_INTERPRETATION,
        "dng_calibration": DNG_TAGS_INTERPRETATION,
        "exif_camera": EXIF_TAGS_INTERPRETATION,
        "gps_location": GPS_TAGS_INTERPRETATION,
        "xmp_camera": CAMERA_XMP_INTERPRETATION,
        "xmp_micasense": MICASENSE_XMP_INTERPRETATION,
        "xmp_dls": DLS_XMP_INTERPRETATION,
        "proprietary": PROPRIETARY_TAGS_INTERPRETATION,
    }
    
    interp_map = interpretation_maps.get(group_name, {})
    
    # Try exact match first
    if tag_name in interp_map:
        return interp_map[tag_name]
    
    # Try numeric tag for proprietary
    try:
        tag_id = int(tag_name)
        if tag_id in interp_map:
            return interp_map[tag_id]
    except (ValueError, TypeError):
        pass
    
    return ""


def get_all_interpretations() -> dict:
    """
    Get all interpretation dictionaries combined.
    
    Returns:
        Dictionary mapping group names to their interpretation dictionaries
    """
    return {
        "basic_info": BASIC_INFO_INTERPRETATION,
        "tiff_structure": TIFF_TAGS_INTERPRETATION,
        "dng_calibration": DNG_TAGS_INTERPRETATION,
        "exif_camera": EXIF_TAGS_INTERPRETATION,
        "gps_location": GPS_TAGS_INTERPRETATION,
        "xmp_camera": CAMERA_XMP_INTERPRETATION,
        "xmp_micasense": MICASENSE_XMP_INTERPRETATION,
        "xmp_dls": DLS_XMP_INTERPRETATION,
        "proprietary": PROPRIETARY_TAGS_INTERPRETATION,
    }


def print_metadata_with_interpretation(groups: MetadataGroups) -> None:
    """Print metadata with interpretations in a formatted way."""
    all_data = groups.to_dict()
    interpretations = get_all_interpretations()
    
    for group_name, group_data in all_data.items():
        if not group_data:
            continue
        
        print(f"\n{'=' * 60}")
        print(f" {group_name.upper().replace('_', ' ')}")
        print('=' * 60)
        
        group_interp = interpretations.get(group_name, {})
        
        for key, value in group_data.items():
            # Format value for display
            if isinstance(value, list) and len(value) > 5:
                value_str = f"[{value[0]}, {value[1]}, ... ({len(value)} items)]"
            elif isinstance(value, str) and len(value) > 80:
                value_str = f"{value[:77]}..."
            else:
                value_str = str(value)
            
            # Get interpretation
            interp = group_interp.get(key, "")
            if not interp:
                try:
                    interp = group_interp.get(int(key), "")
                except (ValueError, TypeError):
                    pass
            
            print(f"\n  {key}: {value_str}")
            if interp:
                print(f"    → {interp}")


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    import json
    import sys
    
    # Example usage
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        image_path = "data/IMG_0010_5.tif"
    
    print("=" * 60)
    print(" MICASENSE METADATA EXTRACTOR")
    print("=" * 60)
    
    # Extract grouped metadata
    try:
        metadata = extract_grouped_metadata(image_path)
        
        # Print with interpretations
        print_metadata_with_interpretation(metadata)
        
        # Show camera specs if MicaSense
        model = metadata.tiff_structure.get("Model", "")
        if model:
            specs = get_camera_specs(model)
            if specs:
                print("\n" + "=" * 60)
                print(" CAMERA SPECIFICATIONS")
                print("=" * 60)
                print(f"  Model: {model}")
                print(f"  Description: {specs.get('description', 'N/A')}")
                print(f"  DLS Version: {specs.get('dls_version', 'N/A')}")
                print(f"  Has Panchromatic: {specs.get('has_panchromatic', False)}")
                print(f"  Has Thermal: {specs.get('has_thermal', False)}")
                print(f"  Bands:")
                for idx, band in specs.get('bands', {}).items():
                    wl = band.get('wavelength', 'N/A')
                    bw = band.get('bandwidth', 'N/A')
                    print(f"    {idx}: {band['name']} - {wl} nm ± {bw} nm")
        
        # Export as JSON
        print("\n" + "=" * 60)
        print(" JSON EXPORT (truncated)")
        print("=" * 60)
        
        metadata_dict = metadata.to_dict()
        print(json.dumps(metadata_dict, indent=2, default=str)[:2000] + "...")
        
        # GPS summary
        print("\n" + "=" * 60)
        print(" GPS COORDINATES")
        print("=" * 60)
        gps = metadata.gps_location
        if "_coordinates_readable" in gps:
            print(f"  Location: {gps['_coordinates_readable']}")
            print(f"  Altitude: {gps.get('GPSAltitude', 'N/A')} m")
        else:
            print("  No GPS data found")
        
    except FileNotFoundError:
        print(f"Error: File not found: {image_path}")
        print("\nUsage: python metadata_extractor.py <image_path>")
        print("\nExample:")
        print("  python metadata_extractor.py /path/to/IMG_0001_1.tif")
