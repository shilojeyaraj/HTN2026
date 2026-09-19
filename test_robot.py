from robomaster import robot
import cv2


ep = robot.Robot()

print("Connecting...")
ep.initialize(conn_type="ap")
print("Connected!")
ep.camera.start_video_stream(display=True)
frame = ep.camera.read_cv2_image(strategy="newest")
#cv2.imwrite("frame.jpg", frame)

#ep.camera.stop_video_stream()
print("camera offf")
#ep.close()

    # ep.chassis.move(
    #     x=-3,
    #     y=0,
    #     z=0,
    #     xy_speed=0.7
    # ).wait_for_completed()

    # ep.chassis.move(
    #     x=0,
    #     y=-1,
    #     z=0,
    #     xy_speed=0.7
    # ).wait_for_completed()


    # ep.chassis.move(
    #     x=0,
    #     y=0,
    #     z=1,
    #     xy_speed=0.7
    # ).wait_for_completed()

#     print("Movement complete")

# finally:
#     ep.close()
