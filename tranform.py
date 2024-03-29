import colorsys
import ctypes
from itertools import product
from multiprocessing import Process, Array
from PIL import Image, ImageDraw, ImageFilter
import random
from scipy.spatial import Delaunay
import sys

POINT_COUNT = 150
EDGE_THRESHOLD = 172
EDGE_RATIO = .98
DARKENING_FACTOR = 35
SPEEDUP_FACTOR_X = 1
SPEEDUP_FACTOR_Y = 1
CONCURRENCY_FACTOR = 3


def main():
    if len(sys.argv) != 2 or not sys.argv[1]:
        print("Please provide the name of the file to process as an argument")
        return 1

    im = Image.open(sys.argv[1])

    points = []
    generate_random(im, points)

    generate_edges(im, points)

    triangles, colors = triangulate(im, points)

    draw(im, points, triangles, colors)

    im.save("result.jpg", "jpeg", quality=95)
    return 0


def generate_random(im, points):
    prop_x, prop_y = get_point_propagation(*im.size)
    point_distance = get_point_distance(*im.size)
    for _ in range(POINT_COUNT):
        x = random.randrange(round((im.size[0] + prop_x) / point_distance)) * \
            point_distance - (prop_x / 2)
        y = random.randrange(round((im.size[1] + prop_y) / point_distance)) * \
            point_distance - (prop_y / 2)
        points.append([x, y])


def get_point_propagation(width, height):
    return width / 4, height / 4


def get_point_distance(width, height):
    return min(width, height) / 16


def generate_edges(im, points):
    im_edges = im.filter(ImageFilter.SHARPEN).filter(ImageFilter.FIND_EDGES)
    for x, y in product(range(im.size[0] - 1), range(im.size[1] - 1)):
        if get_grayscale(*im_edges.getpixel((x, y))) > EDGE_THRESHOLD and \
                random.random() > EDGE_RATIO:
            points.append([x, y])


def get_grayscale(r, g, b):
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def triangulate(im, points):
    triangles = Delaunay(points)
    colors = Array(ctypes.c_uint64, im.size[0] * im.size[1], lock=True)
    jobs = []
    for i in range(CONCURRENCY_FACTOR):
        p = Process(target=triangulate_worker, args=(im, triangles, colors, i,
                                                     CONCURRENCY_FACTOR))
        jobs.append(p)
        p.start()
    for i in jobs:
        i.join()
    decoded_colors = [None] * len(triangles.simplices)
    # Color decoding
    for i, c in enumerate(colors):
        t = (c & 0xFFFF << 32) >> 32
        if t == 0xFFFF:
            continue
        if not decoded_colors[t]:
            decoded_colors[t] = []
        decoded_colors[t].append((c & 0xFF,
                                  (c & 0xFF00) >> 8,
                                  (c & 0xFF0000) >> 16))
    return (triangles, decoded_colors)


def triangulate_worker(im, triangles, colors, worker_index, worker_count):
    for x, y in product(range(SPEEDUP_FACTOR_X,
                              im.size[0] - 1,
                              SPEEDUP_FACTOR_X),
                        # Workers treat different rows
                        range(worker_index * SPEEDUP_FACTOR_Y,
                              im.size[1] - 1,
                              worker_count * SPEEDUP_FACTOR_Y)
                        ):
        t = triangles.find_simplex((x, y)).flat[0]
        pixel_index = y * im.size[0] + x
        colors[pixel_index] = 0xFFFF << 32
        if not ~t:
            continue

        (r, g, b) = im.getpixel((x, y))
        colors[pixel_index] = ((t << 32) + (b << 16) + (g << 8) + r)
    return


def draw(im, points, triangles, colors):
    d = ImageDraw.Draw(im)
    for t, t_colors in enumerate(colors):
        end = (0, 0, 0)
        if t_colors:
            avg = [round(sum(y) / len(y)) for y in zip(*t_colors)]

            (h, s, v) = colorsys.rgb_to_hsv(avg[0], avg[1], avg[2])
            end = colorsys.hsv_to_rgb(h, s,
                                      v - random.random() * DARKENING_FACTOR)
        d.polygon([tuple(points[y]) for y in triangles.simplices[t]],
                  fill=tuple(map(lambda x: round(x), end)))


if __name__ == "__main__":
    sys.exit(main())
