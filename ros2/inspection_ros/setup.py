from setuptools import find_packages, setup


setup(
    name="inspection_ros",
    version="0.1.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/inspection_ros"]),
        ("share/inspection_ros", ["package.xml"]),
    ],
    install_requires=["setuptools", "vision-dimensional-inspection"],
    extras_require={"test": ["pytest>=8,<10"]},
    zip_safe=False,
    maintainer="Sánta Roland",
    maintainer_email="santaroland7@gmail.com",
    description="Publish a repeated synthetic grayscale inspection fixture",
    license="Unspecified",
    entry_points={
        "console_scripts": [
            "synthetic_camera = inspection_ros.synthetic_camera:main",
        ],
    },
)
