import exifread
import os

def check_metadata(image_path):
    results = {
        "has_exif": False,
        "camera_make": None,
        "camera_model": None,
        "date_taken": None,
        "editing_software": None,
        "flags": [],
        "suspicion_score": 0
    }

    suspicion = 0

    try:
        with open(image_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)

        if not tags:
            # WhatsApp strips metadata, so lower penalty
            results["flags"].append("No metadata found (may be WhatsApp stripped)")
            suspicion += 25
        else:
            results["has_exif"] = True

            if 'Image Make' in tags:
                results["camera_make"] = str(tags['Image Make'])
            else:
                results["flags"].append("No camera brand found")
                suspicion += 8

            if 'Image Model' in tags:
                results["camera_model"] = str(tags['Image Model'])

            if 'EXIF DateTimeOriginal' in tags:
                results["date_taken"] = str(tags['EXIF DateTimeOriginal'])
            else:
                results["flags"].append("No date/time found")
                suspicion += 8

            if 'Image Software' in tags:
                software = str(tags['Image Software'])
                results["editing_software"] = software

                editing_tools = [
                    'photoshop', 'lightroom', 'gimp',
                    'picsart', 'snapseed', 'canva', 'affinity'
                ]

                if any(tool in software.lower() for tool in editing_tools):
                    results["flags"].append(f"Edited with: {software}")
                    suspicion += 35

    except Exception as e:
        results["flags"].append(f"Metadata read error: {str(e)}")
        suspicion += 15

    results["suspicion_score"] = min(suspicion, 100)
    return results


def interpret_metadata(score):
    if score < 20:
        return "Metadata looks normal — appears camera-generated", "green"
    elif score < 50:
        return "Some metadata irregularities detected — review recommended", "orange"
    else:
        return "Metadata highly suspicious — likely manipulated or AI-generated", "red"
