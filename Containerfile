# Official ROS Humble ros-base on Jammy; tested platform: linux/amd64.
FROM docker.io/library/ros:humble-ros-base-jammy@sha256:fea7dd1577580a53209dc2e9456cd8d6ef13704a09a8f12914e0867f6861ea9a

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Keep Ubuntu's Python ABI and expose the apt-installed ROS dependencies.
RUN python3 -m venv --system-site-packages /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY constraints/humble.txt /opt/constraints/humble.txt
RUN python -m pip install --constraint /opt/constraints/humble.txt \
    pip setuptools wheel build pytest numpy opencv-python-headless

WORKDIR /workspace
COPY . .
# build's default flow creates an sdist, then builds the wheel from that sdist.
RUN python -m build --no-isolation \
    && python -m pip install --constraint /opt/constraints/humble.txt dist/*.whl \
    && python -m pip check

# Supply --build-context inspection_ros=./ros2/inspection_ros (see README).
COPY --from=inspection_ros /package.xml /setup.py /setup.cfg /opt/inspection_ws/src/inspection_ros/
COPY --from=inspection_ros /resource/inspection_ros /opt/inspection_ws/src/inspection_ros/resource/inspection_ros
COPY --from=inspection_ros /inspection_ros/*.py /opt/inspection_ws/src/inspection_ros/inspection_ros/
COPY --from=inspection_ros /test/*.py /opt/inspection_ws/src/inspection_ros/test/
# colcon and its ament_python support are already in the pinned ros-base image.
# Invoke colcon with the venv interpreter so installed entrypoints use it too.
RUN . /opt/ros/humble/setup.sh \
    && cd /opt/inspection_ws \
    && python /usr/bin/colcon build --packages-select inspection_ros \
    && python -m pip check

# The inherited official entrypoint sources /opt/ros/humble/setup.bash.
CMD ["bash"]
