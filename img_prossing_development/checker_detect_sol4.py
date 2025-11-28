import cv2
import numpy as np

### Define Known checkerboard size ###
CHECKERBOARD_SQUARES = (15, 10)  # number of squares, not inner corners

### Load image ###
img = cv2.imread("checkerboard.jpg")
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

### Step 1: Preprocess ###
blur = cv2.GaussianBlur(gray, (5, 5), 0)

### Step 2: Detect corners using goodFeaturesToTrack function ###
# Jianbo Shi and Carlo Tomasi. Good features to track. In Computer Vision and Pattern Recognition, 1994. Proceedings CVPR'94.
# https://docs.opencv.org/3.4/dd/d1a/group__imgproc__feature.html#ga1d6bb77486c8f92d79c8793ad995d541
# 1. calculate the corner quality using conrnerMinEigenVal or cornerHarris depending on useHarrisDetector
# 2. performs a non-maximum suppression (the local maximums in 3 x 3 neighborhood are retained).
# 3. corners with the minimal eigenvalue less than "qualityLevel" are rejected.
# 4. The remaining corners are sorted by the quality measure in the descending order.
# 5. throws away each corner for which there is a stronger corner at a distance less than "maxDistance".
corners = cv2.goodFeaturesToTrack(
    gray, maxCorners=200, qualityLevel=0.05, minDistance=10
)
corners = np.int0(corners) if corners is not None else []

corners = corners.reshape(-1, 2)

corner_vis = img.copy()
for (x, y) in corners.astype(int):
    cv2.circle(corner_vis, (int(x), int(y)), 2, (0, 0, 255), -1)

cv2.imshow("All corners", corner_vis)
cv2.waitKey(0)


# --- Step 2: Remove gross outliers before PCA ---
# Compute the median position of all detected corners — this serves as a robust
# central estimate that is less sensitive to outliers than the mean.
median = np.median(corners, axis=0)

# Compute the Median Absolute Deviation (MAD), a robust measure of spread.
# MAD = median(|x_i - median(x)|)
mad = np.median(np.abs(corners - median), axis=0)

# Compute a “robust z-score” for each corner, dividing its deviation from the median
# by the MAD. Points with large z-scores are likely outliers.
robust_z = np.abs((corners - median) / (mad + 1e-6))

# Keep only corners within a reasonable threshold (e.g., |z| < 3)
mask = (robust_z[:, 0] < 3) & (robust_z[:, 1] < 3)
corners = corners[mask]

corner_vis = img.copy()
for (x, y) in corners.astype(int):
    cv2.circle(corner_vis, (int(x), int(y)), 2, (255, 0, 0), -1)

cv2.imshow("Post Outlier removal", corner_vis)
cv2.waitKey(0)

''' USE checkerboard pre-knowledge to filter the detected points further'''

### Step 3: PCA to find checkerboard orientation ###
# Use Principal Component Analysis (PCA) to give us the two main orthogonal directions 
# (eigenvectors) that best describe the spread of the corner points (xy coords).
# The mean is the centroid of all corners, and eigvecs are the rotation basis.
mean, eigvecs = cv2.PCACompute(corners.astype(np.float32), mean=None)
## project the corner points into this PCA-aligned coordinate system to analyse geometry.
rotated = (corners - mean) @ eigvecs 

### Step 4: Filter by aspect ratio ###
# Compute bounding box in PCA space
x_min, y_min = rotated.min(axis=0)
x_max, y_max = rotated.max(axis=0)
width = x_max - x_min
height = y_max - y_min
aspect = width / height

expected_aspect = CHECKERBOARD_SQUARES[0] / CHECKERBOARD_SQUARES[1]
print(f"Measured aspect: {aspect:.2f}, expected: {expected_aspect:.2f}")

# Reject corners outside the main rectangular area
mask = (
    (rotated[:, 0] > x_min + 0.05 * width)
    & (rotated[:, 0] < x_max - 0.05 * width)
    & (rotated[:, 1] > y_min + 0.05 * height)
    & (rotated[:, 1] < y_max - 0.05 * height)
)
filtered = corners[mask]

### Step 4: Visualize filtered corners ###
filtered_vis = img.copy()
for (x, y) in filtered:
    cv2.circle(filtered_vis, (int(x), int(y)), 2, (0, 255, 0), -1)

### Step 5: Compute center of checkerboard ###
center = filtered.mean(axis=0).astype(int)
cv2.circle(filtered_vis, tuple(center), 5, (255, 255, 0), -1)

### Step 6: Draw bounding box for visual check ###
rect = cv2.minAreaRect(filtered.astype(np.float32))
box = np.int0(cv2.boxPoints(rect))
cv2.drawContours(filtered_vis, [box], 0, (255, 0, 0), 2)

### Step 7: Display results ###
cv2.imshow("Filtered Corners", filtered_vis)
cv2.waitKey(0)
cv2.destroyAllWindows()