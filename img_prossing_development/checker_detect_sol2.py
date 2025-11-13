import cv2
import numpy as np
import os

# Checkerboard dimensions (inner corners, NOT squares)
CHECKERBOARD = (7, 7)

# Load image
img_path = "checkerboard.jpg"
image = cv2.imread(img_path)

if image is None:
    raise FileNotFoundError(f"Could not load image: {img_path}")

# Resize for easier visualization (optional)
scale = 0.5
image = cv2.resize(image, None, fx=scale, fy=scale)

# --- Step 1: Convert to grayscale ---
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
cv2.imshow("1. Grayscale", gray)

# --- Step 2: Normalize contrast ---
gray_norm = cv2.equalizeHist(gray)
cv2.imshow("2. Equalized", gray_norm)

# --- Step 3: Blur to reduce noise ---
blur = cv2.GaussianBlur(gray_norm, (5, 5), 0)
cv2.imshow("3. Blurred", blur)

# --- Step 4: Edge detection (for visualization) ---
edges = cv2.Canny(blur, 50, 150)
cv2.imshow("4. Canny Edges", edges)

# --- Step 5: Adaptive threshold (binary view of the pattern) ---
thresh = cv2.adaptiveThreshold(
    blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 11, 2
)
cv2.imshow("5. Adaptive Threshold", thresh)

# --- Step 6: Try to find checkerboard corners on different versions ---
found, corners = cv2.findChessboardCornersSB(blur, CHECKERBOARD,
    flags=cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_EXHAUSTIVE)

if not found:
    # Try again with the thresholded image (sometimes works better)
    found, corners = cv2.findChessboardCornersSB(thresh, CHECKERBOARD,
        flags=cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_EXHAUSTIVE)

# --- Step 7: Visualization of result ---
output = image.copy()

if found:
    print(f"Checkerboard found! {len(corners)} corners detected.")
    cv2.drawChessboardCorners(output, CHECKERBOARD, corners, found)
else:
    print("Checkerboard not found — check intermediate images for contrast issues.")

cv2.imshow("6. Final Detection", output)

cv2.waitKey(0)
cv2.destroyAllWindows()
