import cv2
import numpy as np

# --- Load image ---
img = cv2.imread("checkerboard.jpg")
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# --- Step 1: Preprocess ---
blur = cv2.GaussianBlur(gray, (5, 5), 0)
edges = cv2.Canny(blur, 50, 150)

# --- Step 2: Detect corners using goodFeaturesToTrack function ---
# Jianbo Shi and Carlo Tomasi. Good features to track. In Computer Vision and Pattern Recognition, 1994. Proceedings CVPR'94.
# https://docs.opencv.org/3.4/dd/d1a/group__imgproc__feature.html#ga1d6bb77486c8f92d79c8793ad995d541
# 1. calculate the corner quality using conrnerMinEigenVal or cornerHarris depending on useHarrisDetector
# 2. performs a non-maximum suppression (the local maximums in 3 x 3 neighborhood are retained).
# 3. corners with the minimal eigenvalue less than "qualityLevel" are rejected.
# 4. The remaining corners are sorted by the quality measure in the descending order.
# 5. throws away each corner for which there is a stronger corner at a distance less than "maxDistance".
corners = cv2.goodFeaturesToTrack(
    gray, maxCorners=200, qualityLevel=0.05, minDistance=10, useHarrisDetector=True
)
corners = np.int0(corners) if corners is not None else []

corner_vis = img.copy()
for i in corners:
    x, y = i.ravel()
    cv2.circle(corner_vis, (x, y), 3, (0, 0, 255), -1)

# --- Step 3: Find contours for structure visualization ---
contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

contour_vis = img.copy()
cv2.drawContours(contour_vis, contours, -1, (0, 255, 0), 1)

# --- Step 4: Combine corner + edge info to find checkerboard area ---
mask = np.zeros_like(gray)
cv2.drawContours(mask, contours, -1, 255, 1)
points = np.array([i.ravel() for i in corners])
for (x, y) in points:
    if mask[y, x] > 0:
        cv2.circle(mask, (x, y), 2, 255, -1)

# --- Step 5: Find bounding box of dense region ---
nonzero = np.argwhere(mask > 0)
if len(nonzero) > 0:
    y_min, x_min = nonzero.min(axis=0)
    y_max, x_max = nonzero.max(axis=0)
    center = ((x_min + x_max) // 2, (y_min + y_max) // 2)
    # cv2.rectangle(img, (x_min, y_min), (x_max, y_max), (255, 0, 0), 2)
    cv2.circle(img, center, 5, (0, 255, 255), -1)
    print(f"Checkerboard approximate center: {center}")
else:
    print("No dense grid-like region found")

# --- Step 6: Display results ---
cv2.imshow("1. Grayscale", gray)
print(gray.shape)
# cv2.waitKey(0)
cv2.imshow("2. Edges", edges)
print(edges.shape)
# cv2.waitKey(0)
cv2.imshow("3. Corners", corner_vis)
print(corner_vis.shape)
# cv2.waitKey(0)
cv2.imshow("4. Contours", contour_vis)
print(contour_vis.shape)
# cv2.waitKey(0)
cv2.imshow("5. Final Detected Region", img)
cv2.waitKey(0)

cv2.destroyAllWindows()
